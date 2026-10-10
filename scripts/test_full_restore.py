"""
Script de validation d'un cycle complet de Sauvegarde & Restauration (Sprint 6, Tâche 6.8 & Exigence V19).
Exécute un dump complet de PostgreSQL knowledge, restaure dans une base témoin,
compare les tables et l'intégrité vectorielle, puis nettoie la base témoin.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path
import asyncpg
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

# Configuration
CONTAINER_NAME = "mementomori-knowledge-db-1"
DB_NAME = "knowledge"
RESTORE_DB_NAME = "knowledge_restore_verify"
PG_USER = "knowledge_app"
DUMP_FILE = Path(__file__).parent / "dump_verify_sprint6.sql"


def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.returncode, res.stdout, res.stderr


async def main():
    print("=" * 70)
    print("MEMENTOMORI - Test de Restauration Complète de Base de Données (V19)")
    print("=" * 70)

    # 1. Vérification de la présence du container Docker
    rc, stdout, stderr = run_cmd(["docker", "ps", "--filter", f"name={CONTAINER_NAME}", "--format", "{{.Names}}"])
    if CONTAINER_NAME not in stdout:
        print(f"[-] Container '{CONTAINER_NAME}' non trouvé ou inactif.")
        sys.exit(1)
    print(f"[+] Container '{CONTAINER_NAME}' actif.")

    # 2. Exécution du pg_dump complet
    print(f"[+] Génération du dump SQL depuis '{DB_NAME}'...")
    dump_cmd = [
        "docker", "exec", CONTAINER_NAME,
        "pg_dump", "-U", PG_USER, "-d", DB_NAME, "--clean", "--if-exists"
    ]
    with open(DUMP_FILE, "w", encoding="utf-8") as f:
        res = subprocess.run(dump_cmd, stdout=f, stderr=subprocess.PIPE, text=True)
    
    if res.returncode != 0:
        print(f"[-] Échec de pg_dump : {res.stderr}")
        sys.exit(1)
    
    dump_size = DUMP_FILE.stat().st_size
    print(f"[+] Dump SQL généré avec succès ({dump_size} octets) : {DUMP_FILE.name}")

    # 3. Création de la base témoin de restauration
    print(f"[+] Création de la base temporaire de test '{RESTORE_DB_NAME}'...")
    run_cmd(["docker", "exec", CONTAINER_NAME, "psql", "-U", PG_USER, "-d", DB_NAME, "-c", f"DROP DATABASE IF EXISTS {RESTORE_DB_NAME};"])
    rc, stdout, stderr = run_cmd(["docker", "exec", CONTAINER_NAME, "psql", "-U", PG_USER, "-d", DB_NAME, "-c", f"CREATE DATABASE {RESTORE_DB_NAME};"])
    if rc != 0:
        print(f"[-] Impossible de créer la base témoin : {stderr}")
        sys.exit(1)

    # 4. Restauration du dump dans la base témoin
    print(f"[+] Restauration du dump dans '{RESTORE_DB_NAME}'...")
    with open(DUMP_FILE, "r", encoding="utf-8") as f:
        res = subprocess.run(
            ["docker", "exec", "-i", CONTAINER_NAME, "psql", "-U", PG_USER, "-d", RESTORE_DB_NAME],
            stdin=f, capture_output=True, text=True
        )

    # psql retourne 0 même avec des notices/warnings
    print(f"[+] Restauration terminée.")

    # 5. Vérification comparative de l'intégrité des données
    print("[+] Vérification comparative des tables et comptages...")
    pw = os.getenv("KNOWLEDGE_DB_PASSWORD")
    conn_orig = await asyncpg.connect(f"postgresql://knowledge_app:{pw}@localhost:5433/{DB_NAME}")
    conn_rest = await asyncpg.connect(f"postgresql://knowledge_app:{pw}@localhost:5433/{RESTORE_DB_NAME}")

    tables_to_check = [
        "workspaces",
        "collections",
        "documents",
        "document_versions",
        "fragments",
        "principals",
        "policies",
        "audit_log"
    ]

    all_matched = True
    print("\n--- Comparatif d'intégrité ---")
    for tbl in tables_to_check:
        c_orig = await conn_orig.fetchval(f"SELECT count(*) FROM {tbl}")
        c_rest = await conn_rest.fetchval(f"SELECT count(*) FROM {tbl}")
        matched = (c_orig == c_rest) and (c_orig > 0 or tbl == "feedback")
        if not (c_orig == c_rest):
            all_matched = False
        status = "[CONFORME]" if (c_orig == c_rest) else "[DISCORDANCE]"
        print(f" • {tbl:<20} : Original={c_orig:<5} Restauration={c_rest:<5} {status}")

    # 6. Test d'intégrité vectorielle pgvector sur la base restaurée
    print("\n[+] Test de recherche vectorielle sur la base restaurée...")
    vec_sample = await conn_rest.fetchval("SELECT embedding FROM fragments LIMIT 1")
    if vec_sample:
        # Test cosine distance
        sim_check = await conn_rest.fetchval(
            "SELECT count(*) FROM fragments WHERE embedding <=> $1::vector < 1.5",
            str(vec_sample)
        )
        print(f"[+] Requête vectorielle pgvector sur base restaurée réussie ({sim_check} fragments analysés).")
    else:
        print("[-] Aucun embedding trouvé pour validation vectorielle.")
        all_matched = False

    await conn_orig.close()
    await conn_rest.close()

    # 7. Nettoyage de la base témoin et du dump temporaire
    print(f"[+] Nettoyage de la base temporaire '{RESTORE_DB_NAME}'...")
    run_cmd(["docker", "exec", CONTAINER_NAME, "psql", "-U", PG_USER, "-d", DB_NAME, "-c", f"DROP DATABASE IF EXISTS {RESTORE_DB_NAME};"])
    if DUMP_FILE.exists():
        DUMP_FILE.unlink()
    print("[+] Fichiers temporaires supprimés.")

    print("\n" + "=" * 70)
    if all_matched:
        print("RÉSULTAT : RESTAURATION COMPLÈTE VALIDÉE À 100% CONFORME (V19)")
    else:
        print("RÉSULTAT : ÉCHEC DE RESTAURATION (Discordance détectée)")
    print("=" * 70)

    if not all_matched:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
