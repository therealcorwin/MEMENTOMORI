"""
Configuration de la taxonomie initiale Paperless-ngx pour MEMENTOMORI (Sprint 2).
Crée les types de documents, les tags par workspace, scope et sensibilité.
"""

from documents.models import DocumentType, Tag

# 1. Types de documents
DOCUMENT_TYPES = [
    "Règlement",
    "Contrat",
    "Facture",
    "Procès-Verbal",
    "Devis",
    "Sinistre",
    "Email",
    "Courrier",
    "Relevé bancaire",
    "Santé",
    "Statuts / Juridique",
    "Technique / Code",
]

print("--- Création des types de documents ---")
for dt_name in DOCUMENT_TYPES:
    dt, created = DocumentType.objects.get_or_create(name=dt_name)
    print(f"Type '{dt.name}': {'créé' if created else 'existant'}")

# 2. Tags par Workspace
WORKSPACE_TAGS = [
    ("ws:copro-jardins", "#1f77b4"),
    ("ws:finances-perso", "#2ca02c"),
    ("ws:sante", "#d62728"),
    ("ws:admin-perso", "#9467bd"),
    ("ws:dev", "#8c564b"),
    ("ws:consulting", "#e377c2"),
    ("ws:veille", "#7f7f7f"),
    ("ws:entreprise", "#bcbd22"),
    ("ws:formation", "#17becf"),
]

# 3. Tags par Scope
SCOPE_TAGS = [
    ("scope:collectif", "#3498db"),
    ("scope:cs", "#e67e22"),
    ("scope:administration", "#9b59b6"),
    ("scope:owner", "#2ecc71"),
]

# 4. Tags par Sensibilité
SENSITIVITY_TAGS = [
    ("sens:public", "#2ecc71"),
    ("sens:interne", "#f1c40f"),
    ("sens:confidentiel", "#e67e22"),
    ("sens:secret", "#e74c3c"),
]

print("\n--- Création des tags ---")
all_tags = WORKSPACE_TAGS + SCOPE_TAGS + SENSITIVITY_TAGS
for tag_name, color in all_tags:
    tag, created = Tag.objects.get_or_create(name=tag_name, defaults={"color": color})
    print(f"Tag '{tag.name}': {'créé' if created else 'existant'}")

print("\nTaxonomie Paperless-ngx initialisée avec succès !")
