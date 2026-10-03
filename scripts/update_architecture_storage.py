"""
Met à jour src/architecture_base_connaissances.md pour intégrer
le principe P7 et la structure physique D:\Dev\Docker\MEMENTOMORI dans la section 10.
"""

from pathlib import Path

arch_path = Path("src/architecture_base_connaissances.md")
content = arch_path.read_text(encoding="utf-8")

# 1. Ajout de P7 dans le tableau des principes (§2)
p6_line = "| P6 | **Moindre privilège par agent**"
p7_block = (
    "| P6 | **Moindre privilège par agent** — chaque agent ne peut lire QUE les workspaces qui lui sont explicitement autorisés. | Chaque service account (OAuth2) a un scope JWT limité aux workspaces déclarés. |\n"
    "| P7 | **Stockage Docker centralisé et compartimenté** — la racine de persistance de tous les conteneurs est localisée sur `D:\\Dev\\Docker\\MEMENTOMORI`. Chaque conteneur possède son propre dossier dédié avec des sous-répertoires typés (`bdd`, `data`, `config`, `cert`, `media`, etc.). Pas de volumes anonymes. | Persistance prédictible, sauvegardes ciblées simplifiées, isolation physique des données sur l'hôte. |\n"
)

if "| P7 |" not in content:
    lines = content.splitlines(keepends=True)
    new_lines = []
    for line in lines:
        if line.startswith(p6_line):
            new_lines.append(p7_block)
        else:
            new_lines.append(line)
    content = "".join(new_lines)
    print("Principe P7 ajouté dans la Section 2.")

# 2. Ajout de la documentation d'arborescence Docker dans la Section 10
storage_section = """### 10.2 Structure de stockage physique des conteneurs (`D:\\Dev\\Docker\\MEMENTOMORI`)

Conformément au principe **P7**, la racine de stockage de l'ensemble des conteneurs est fixée à `D:\\Dev\\Docker\\MEMENTOMORI`. Les fichiers de configuration actifs (`docker-compose.yml` et `.env`) y résident, et chaque conteneur dispose de son propre répertoire avec des sous-dossiers typés :

```text
D:\\Dev\\Docker\\MEMENTOMORI\\
├── docker-compose.yml         # Compose d'orchestration locale
├── .env                       # Variables et secrets centralisés
├── knowledge-db\\
│   ├── bdd\\                  # Données PostgreSQL 16 (pgvector)
│   └── config\\               # Script 01_init.sql
├── knowledge-redis\\
│   └── data\\                 # Données Redis (file arq, cache)
├── authentik-server\\
│   ├── cert\\                 # Certificats SSL/JWT
│   └── config\\
├── authentik-db\\
│   └── bdd\\                  # Données PostgreSQL Authentik
├── authentik-redis\\
│   └── data\\                 # Données Redis Authentik
├── paperless\\
│   ├── data\\                 # Données applicatives Paperless
│   ├── media\\                # Originaux & aperçus PDF/scans
│   ├── consume\\              # Dossier de dépôt automatique
│   └── export\\               # Exports
├── paperless-db\\
│   └── bdd\\                  # Données PostgreSQL Paperless
├── paperless-redis\\
│   └── data\\
├── traefik\\
│   ├── cert\\                 # acme.json (Let's Encrypt)
│   └── config\\               # Configurations dynamiques
├── prometheus\\
│   ├── config\\               # prometheus.yml
│   └── data\\                 # Métriques TSDB
├── grafana\\
│   ├── config\\               # Provisioning datasources & dashboards
│   └── data\\                 # Base Grafana
├── loki\\
│   ├── config\\               # loki-config.yml
│   └── data\\                 # Chunks de logs
├── promtail\\
│   └── config\\               # promtail-config.yml
└── uptime-kuma\\
    └── data\\                 # Base SQLite et sondes Uptime Kuma
```

"""

if "### 10.2 Structure de stockage physique" not in content:
    content = content.replace("### 10.2 Docker Compose", storage_section + "### 10.3 Docker Compose")
    content = content.replace("### 10.3 Variables d'environnement", "### 10.4 Variables d'environnement")
    print("Documentation de l'arborescence Docker ajoutée dans la Section 10.")

arch_path.write_text(content, encoding="utf-8")
print("Mise à jour terminée avec succès.")
