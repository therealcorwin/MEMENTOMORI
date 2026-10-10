"""Script d'enregistrement et de vérification des bases MEMENTOMORI dans Databasement.

Ce script utilise l'API REST de Databasement (authentifiée par Sanctum Token depuis .env)
pour déclarer automatiquement les serveurs PostgreSQL :
1. MEMENTOMORI_KNOWLEDGE_DB (pgvector, 14 tables)
2. MEMENTOMORI_PAPERLESS_DB (métadonnées Paperless-ngx)
3. MEMENTOMORI_AUTHENTIK_DB (Identités et flux OAuth2)

Et leur appliquer la politique de rétention GFS (Daily / Minuit).
"""

import sys
import httpx
from dotenv import dotenv_values


def setup_databasement():
    config = dotenv_values(".env")
    api_url = config.get("DATABASEMENT_API_URL", "http://localhost:2226").rstrip("/") + "/api/v1"
    token = config.get("DATABASEMENT_API_TOKEN")

    if not token:
        print("[!] DATABASEMENT_API_TOKEN manquant dans le fichier .env")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    client = httpx.Client(timeout=30)

    # 1. Lister les serveurs existants
    resp = client.get(f"{api_url}/database-servers", headers=headers)
    resp.raise_for_status()
    existing_servers = {s["name"]: s for s in resp.json().get("data", [])}

    # 2. Récupérer les schedules et volumes
    schedules = client.get(f"{api_url}/backup-schedules", headers=headers).json().get("data", [])
    volumes = client.get(f"{api_url}/volumes", headers=headers).json().get("data", [])

    schedule_id = next((s["id"] for s in schedules if "Minuit" in s["name"] or "Daily" in s["name"]), schedules[0]["id"])
    volume_id = volumes[0]["id"]

    servers_to_manage = [
        {
            "name": "MEMENTOMORI_KNOWLEDGE_DB",
            "database_type": "postgres",
            "description": "PostgreSQL Knowledge DB (pgvector, 14 tables RAG)",
            "host": "mementomori-knowledge-db-1",
            "port": 5432,
            "username": "knowledge_app",
            "password": config.get("KNOWLEDGE_DB_PASSWORD"),
            "connection_database": "knowledge",
            "dump_format": "custom",
            "dump_privileges": True,
            "backups_enabled": True,
            "backups": [
                {
                    "volume_ids": [volume_id],
                    "path": "MEMENTOMORI_KNOWLEDGE_DB",
                    "backup_schedule_id": schedule_id,
                    "retention_policy": "gfs",
                    "gfs_keep_daily": 7,
                    "gfs_keep_weekly": 4,
                    "gfs_keep_monthly": 12,
                    "database_selection_mode": "selected",
                    "database_names": ["knowledge"],
                }
            ],
        },
        {
            "name": "MEMENTOMORI_PAPERLESS_DB",
            "database_type": "postgres",
            "description": "PostgreSQL Paperless-ngx metadata DB",
            "host": "mementomori-paperless-db-1",
            "port": 5432,
            "username": "paperless",
            "password": config.get("PAPERLESS_DB_PASSWORD"),
            "connection_database": "paperless",
            "dump_format": "custom",
            "dump_privileges": True,
            "backups_enabled": True,
            "backups": [
                {
                    "volume_ids": [volume_id],
                    "path": "MEMENTOMORI_PAPERLESS_DB",
                    "backup_schedule_id": schedule_id,
                    "retention_policy": "gfs",
                    "gfs_keep_daily": 7,
                    "gfs_keep_weekly": 4,
                    "gfs_keep_monthly": 12,
                    "database_selection_mode": "selected",
                    "database_names": ["paperless"],
                }
            ],
        },
        {
            "name": "MEMENTOMORI_AUTHENTIK_DB",
            "database_type": "postgres",
            "description": "PostgreSQL Authentik Identity & OAuth2 DB",
            "host": "mementomori-authentik-db-1",
            "port": 5432,
            "username": "authentik",
            "password": config.get("AUTHENTIK_DB_PASSWORD"),
            "connection_database": "authentik",
            "dump_format": "custom",
            "dump_privileges": True,
            "backups_enabled": True,
            "backups": [
                {
                    "volume_ids": [volume_id],
                    "path": "MEMENTOMORI_AUTHENTIK_DB",
                    "backup_schedule_id": schedule_id,
                    "retention_policy": "gfs",
                    "gfs_keep_daily": 7,
                    "gfs_keep_weekly": 4,
                    "gfs_keep_monthly": 12,
                    "database_selection_mode": "selected",
                    "database_names": ["authentik"],
                }
            ],
        },
        {
            "name": "MEMENTOMORI_KNOWLEDGE_REDIS",
            "database_type": "redis",
            "description": "Redis Cache & File d'ingestion Knowledge",
            "host": "mementomori-knowledge-redis-1",
            "port": 6379,
            "password": config.get("REDIS_PASSWORD"),
            "backups_enabled": True,
            "backups": [
                {
                    "volume_ids": [volume_id],
                    "path": "MEMENTOMORI_KNOWLEDGE_REDIS",
                    "backup_schedule_id": schedule_id,
                    "retention_policy": "gfs",
                    "gfs_keep_daily": 7,
                    "gfs_keep_weekly": 4,
                    "gfs_keep_monthly": 12,
                }
            ],
        },
        {
            "name": "MEMENTOMORI_PAPERLESS_REDIS",
            "database_type": "redis",
            "description": "Redis Broker des tâches Paperless-ngx",
            "host": "mementomori-paperless-redis-1",
            "port": 6379,
            "backups_enabled": True,
            "backups": [
                {
                    "volume_ids": [volume_id],
                    "path": "MEMENTOMORI_PAPERLESS_REDIS",
                    "backup_schedule_id": schedule_id,
                    "retention_policy": "gfs",
                    "gfs_keep_daily": 7,
                    "gfs_keep_weekly": 4,
                    "gfs_keep_monthly": 12,
                }
            ],
        },
    ]

    for server_def in servers_to_manage:
        name = server_def["name"]
        if name in existing_servers:
            server_id = existing_servers[name]["id"]
            print(f"[OK] Serveur {name} déjà configuré dans Databasement (ID: {server_id})")
        else:
            create_resp = client.post(f"{api_url}/database-servers", headers=headers, json=server_def)
            create_resp.raise_for_status()
            server_id = create_resp.json().get("data", {}).get("id")
            print(f"[+] Serveur {name} créé avec succès (ID: {server_id})")

        # Test de connexion
        test_resp = client.get(f"{api_url}/database-servers/{server_id}/test-connection", headers=headers)
        if test_resp.status_code == 200 and test_resp.json().get("success"):
            print(f"   -> Test de connexion : SUCCES ({test_resp.json().get('details', {}).get('ping_ms')}ms)")
        else:
            print(f"   -> [!] Echec test de connexion : {test_resp.text}")


if __name__ == "__main__":
    setup_databasement()
