"""
Configuration initiale OAuth2 dans Authentik pour MEMENTOMORI (Sprint 1).
Crée le Provider OAuth2, l'Application knowledge-api et le compte de service csbot.
"""

from authentik.core.models import Application, User, UserTypes
from authentik.crypto.models import CertificateKeyPair
from authentik.flows.models import Flow
from authentik.providers.oauth2.models import OAuth2Provider, ScopeMapping

# 1. Utilisateur Service Account csbot
user, user_created = User.objects.get_or_create(
    username="csbot",
    defaults={
        "name": "CSBOT Service Account",
        "type": UserTypes.SERVICE_ACCOUNT,
        "is_active": True,
    },
)
print(f"User csbot: {'créé' if user_created else 'existant'} (ID: {user.pk})")

# 2. Flux d'autorisation et certificat
auth_flow = Flow.objects.get(slug="default-provider-authorization-implicit-consent")
signing_cert = CertificateKeyPair.objects.get(name="authentik Internal JWT Certificate")

# 3. Provider OAuth2 pour knowledge-api
provider, prov_created = OAuth2Provider.objects.get_or_create(
    name="knowledge-api",
    defaults={
        "client_type": "confidential",
        "client_id": "csbot",
        "client_secret": "csbot_secret_2026_dev",
        "authorization_flow": auth_flow,
        "signing_key": signing_cert,
    },
)
if not prov_created:
    provider.client_id = "csbot"
    provider.client_secret = "csbot_secret_2026_dev"
    provider.client_type = "confidential"
    provider.authorization_flow = auth_flow
    provider.signing_key = signing_cert
    provider.save()

# Associer les scopes standards OpenID
standard_scopes = ScopeMapping.objects.filter(scope_name__in=["openid", "profile", "email"])
provider.property_mappings.set(standard_scopes)
provider.save()
print(f"Provider OAuth2 'knowledge-api': {'créé' if prov_created else 'mis à jour'}")

# 4. Application knowledge-api
app, app_created = Application.objects.get_or_create(
    slug="knowledge-api",
    defaults={
        "name": "Knowledge API",
        "provider": provider,
    },
)
if not app_created and app.provider != provider:
    app.provider = provider
    app.save()

print(f"Application 'knowledge-api': {'créée' if app_created else 'existante'}")
print("Configuration Authentik terminée avec succès !")
