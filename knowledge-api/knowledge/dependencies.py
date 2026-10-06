"""Dépendances FastAPI : base de données, cache Redis, et Authentification Authentik (Task 3.4)."""

import uuid
from typing import AsyncGenerator, Optional
import httpx
import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from knowledge.config import settings
from knowledge.logging import get_logger
from knowledge.models import Principal, Policy, Workspace

logger = get_logger(__name__)

# Engine et Session async SQLAlchemy
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True
)

async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Générateur de session SQLAlchemy asynchrone."""
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Client JWKS pour Authentik
jwks_client: Optional[PyJWKClient] = None
if settings.AUTHENTIK_JWKS_URL:
    try:
        jwks_client = PyJWKClient(settings.AUTHENTIK_JWKS_URL, cache_keys=True, max_cached_keys=10)
    except Exception as e:
        logger.warning("authentik_jwks_client_init_failed", error=str(e))


class AuthContext:
    """Contexte d'autorisation résolu pour une requête."""
    def __init__(
        self,
        principal: Principal,
        policy: Policy,
        workspace: Workspace
    ):
        self.principal = principal
        self.policy = policy
        self.workspace = workspace

    @property
    def role(self) -> str:
        return self.policy.role

    @property
    def allowed_scopes(self) -> list[str]:
        return self.policy.allowed_scopes or ["owner"]

    @property
    def max_sensitivity(self) -> str:
        return self.policy.max_sensitivity or "interne"

    @property
    def actions(self) -> list[str]:
        return self.policy.actions or ["read"]


async def get_current_principal(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_dev_principal: Optional[str] = Header(None, alias="X-Dev-Principal"),
    db: AsyncSession = Depends(get_db)
) -> Principal:
    """Valide le token JWT Authentik ou utilise le mode dev."""
    # 1. Mode développement / bypass explicite
    if settings.ENVIRONMENT == "development" and x_dev_principal:
        result = await db.execute(
            select(Principal).where(Principal.external_id == x_dev_principal)
        )
        principal = result.scalar_one_or_none()
        if not principal:
            # Création automatique du principal en dev
            principal = Principal(
                type="app" if x_dev_principal == "csbot" else "user",
                external_id=x_dev_principal,
                display_name=f"Dev {x_dev_principal}"
            )
            db.add(principal)
            await db.commit()
            await db.refresh(principal)
        return principal

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="En-tête Authorization manquant ou format invalide (Bearer token attendu)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1]

    # 2. Validation du token JWT Authentik
    external_id: str = ""
    try:
        if jwks_client:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=settings.AUTHENTIK_AUDIENCE,
                options={"verify_aud": False}  # Tolérer audience si service account
            )
            external_id = payload.get("client_id") or payload.get("sub") or payload.get("preferred_username")
        else:
            # Fallback non-vérifié uniquement en DEBUG
            if settings.DEBUG:
                unverified = jwt.decode(token, options={"verify_signature": False})
                external_id = unverified.get("client_id") or unverified.get("sub")
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Client JWKS non configuré"
                )
    except jwt.PyJWTError as e:
        logger.error("jwt_verification_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token JWT invalide ou expiré : {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not external_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiant du principal introuvable dans le token",
        )

    # 3. Récupération ou enregistrement du Principal
    result = await db.execute(
        select(Principal).where(Principal.external_id == external_id)
    )
    principal = result.scalar_one_or_none()

    if not principal:
        principal = Principal(
            type="app" if "csbot" in external_id.lower() else "user",
            external_id=external_id,
            display_name=external_id
        )
        db.add(principal)
        await db.commit()
        await db.refresh(principal)

    return principal


async def get_auth_context(
    workspace_id: uuid.UUID | str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db)
) -> AuthContext:
    """Vérifie les droits du Principal sur le Workspace spécifié (RBAC). Accepte un UUID ou un slug."""
    # 1. Vérifier existence du workspace (par UUID ou slug)
    ws_uuid = None
    if isinstance(workspace_id, uuid.UUID):
        ws_uuid = workspace_id
    else:
        try:
            ws_uuid = uuid.UUID(str(workspace_id))
        except (ValueError, TypeError):
            ws_uuid = None

    if ws_uuid:
        ws_result = await db.execute(
            select(Workspace).where(Workspace.id == ws_uuid)
        )
    else:
        ws_result = await db.execute(
            select(Workspace).where(Workspace.slug == str(workspace_id))
        )

    workspace = ws_result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace '{workspace_id}' introuvable."
        )

    # 2. Vérifier la policy pour ce principal
    pol_result = await db.execute(
        select(Policy).where(
            Policy.workspace_id == workspace.id,
            Policy.principal_id == principal.id
        )
    )
    policy = pol_result.scalar_one_or_none()

    if not policy:
        # En mode DEV, auto-attribution uniquement pour les comptes d'administration explicites
        if settings.ENVIRONMENT == "development" and principal.external_id in ("csbot", "dev_admin", "admin"):
            policy = Policy(
                workspace_id=workspace.id,
                principal_id=principal.id,
                role="admin",
                allowed_scopes=["owner", "copro", "conseil_syndical", "public"],
                actions=["read", "write", "search"],
                max_sensitivity="secret"
            )
            db.add(policy)
            await db.commit()
            await db.refresh(policy)
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accès refusé : aucune policy pour le principal '{principal.external_id}' sur le workspace '{workspace.slug}'."
            )

    return AuthContext(principal=principal, policy=policy, workspace=workspace)
