"""
Configuration OAuth2 / OIDC dans Authentik pour le Frontend Knowledge Dashboard (Sprint 8, Tâche 8.2).
Crée le Provider OAuth2 public (PKCE) et l'Application knowledge-dashboard.
"""

from authentik.core.models import Application
from authentik.crypto.models import CertificateKeyPair
from authentik.flows.models import Flow
from authentik.common.oauth.constants import (
    GRANT_TYPE_AUTHORIZATION_CODE,
    GRANT_TYPE_REFRESH_TOKEN,
)
from authentik.providers.oauth2.models import (
    OAuth2Provider,
    RedirectURI,
    RedirectURIMatchingMode,
    RedirectURIType,
    ScopeMapping,
)

print("=" * 70)
print("Configuration Authentik OIDC pour knowledge-dashboard (Sprint 8)")
print("=" * 70)

# 1. Flux d'autorisation et certificat de signature
auth_flow = Flow.objects.get(slug="default-provider-authorization-implicit-consent")
signing_cert = CertificateKeyPair.objects.get(name="authentik Internal JWT Certificate")

# 2. Définition des URIs de redirection autorisées (Dev Vite, Docker Local 8080 + Prod Traefik)
redirect_targets = [
    ("http://localhost:5173/callback", RedirectURIType.AUTHORIZATION),
    ("http://localhost:5173/", RedirectURIType.LOGOUT),
    ("http://localhost:5173/silent-renew.html", RedirectURIType.AUTHORIZATION),
    ("http://127.0.0.1:5173/callback", RedirectURIType.AUTHORIZATION),
    ("http://127.0.0.1:5173/", RedirectURIType.LOGOUT),
    ("http://localhost:8080/callback", RedirectURIType.AUTHORIZATION),
    ("http://localhost:8080/", RedirectURIType.LOGOUT),
    ("http://localhost:8080/silent-renew.html", RedirectURIType.AUTHORIZATION),
    ("http://127.0.0.1:8080/callback", RedirectURIType.AUTHORIZATION),
    ("http://127.0.0.1:8080/", RedirectURIType.LOGOUT),
    ("http://127.0.0.1:8080/silent-renew.html", RedirectURIType.AUTHORIZATION),
    ("https://dashboard.localhost/callback", RedirectURIType.AUTHORIZATION),
    ("https://dashboard.localhost/", RedirectURIType.LOGOUT),
    ("https://dashboard.localhost/silent-renew.html", RedirectURIType.AUTHORIZATION),
]

redirect_uris = [
    RedirectURI(
        matching_mode=RedirectURIMatchingMode.STRICT,
        url=url,
        redirect_uri_type=uri_type,
    )
    for url, uri_type in redirect_targets
]

# 3. Provider OAuth2 pour knowledge-dashboard
provider, prov_created = OAuth2Provider.objects.get_or_create(
    name="knowledge-dashboard",
    defaults={
        "client_type": "public",  # Client public pour SPA avec PKCE
        "client_id": "knowledge-dashboard",
        "authorization_flow": auth_flow,
        "signing_key": signing_cert,
        "include_claims_in_id_token": True,
    },
)

provider.client_type = "public"
provider.client_id = "knowledge-dashboard"
provider.authorization_flow = auth_flow
provider.signing_key = signing_cert
provider.include_claims_in_id_token = True
provider.redirect_uris = redirect_uris
provider.grant_types = [GRANT_TYPE_AUTHORIZATION_CODE, GRANT_TYPE_REFRESH_TOKEN]
provider.save()

# Associer les scopes standards OpenID (openid, profile, email)
standard_scopes = ScopeMapping.objects.filter(scope_name__in=["openid", "profile", "email"])
provider.property_mappings.set(standard_scopes)
provider.save()

print(f"[+] Provider OAuth2 'knowledge-dashboard': {'créé' if prov_created else 'mis à jour'}")
print(f"    - Type: {provider.client_type}")
print(f"    - Client ID: {provider.client_id}")
print(f"    - Redirect URIs ({len(provider.redirect_uris)}): {[u.url for u in provider.redirect_uris]}")

# 4. Application knowledge-dashboard
app, app_created = Application.objects.get_or_create(
    slug="knowledge-dashboard",
    defaults={
        "name": "Knowledge Dashboard",
        "provider": provider,
    },
)

if not app_created and app.provider != provider:
    app.provider = provider
    app.save()

print(f"[+] Application 'knowledge-dashboard': {'créée' if app_created else 'existante'}")
print("=" * 70)
print("Configuration OIDC Dashboard terminée avec succès !")
print("=" * 70)

