"""Protection de la documentation Swagger / OpenAPI (§16.11, Task 3.18)."""

import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from knowledge.config import settings

security = HTTPBasic()

def verify_docs_credentials(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """Protège l'accès à /docs, /redoc et /openapi.json par HTTP Basic Auth."""
    is_user_correct = secrets.compare_digest(credentials.username, settings.DOCS_USERNAME)
    is_pass_correct = secrets.compare_digest(credentials.password, settings.DOCS_PASSWORD)

    if not (is_user_correct and is_pass_correct):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants d'accès à la documentation incorrects",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
