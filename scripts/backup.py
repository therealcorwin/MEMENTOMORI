"""
Script de Sauvegarde Complète et Rétention GFS Automatisée (Sprint 10, Tâche 10.5 & Exigences B1/B2).

Sauvegarde de manière cohérente :
1. PostgreSQL Knowledge (mementomori-knowledge-db-1)
2. PostgreSQL Paperless (mementomori-paperless-db-1)
3. PostgreSQL Authentik (mementomori-authentik-db-1)
4. Redis Dump RDB (mementomori-knowledge-redis-1, mementomori-paperless-redis-1)
5. SQLite Uptime Kuma (mementomori-uptime-kuma-1:/app/data/kuma.db)
6. Médias et Documents Paperless (/usr/src/paperless/media)

Fonctionnalités :
- Archive consolidée compressée .tar.gz
- Empreinte cryptographique SHA-256 (.sha256)
- Manifeste JSON complet (tailles, hashs, dates, versions)
- Chiffrement optionnel AES-256 (si BACKUP_PASSWORD ou BACKUP_ENCRYPTION_KEY dans .env)
- Politique de rétention GFS (Grand-père / Père / Fils) :
  * 7 sauvegardes quotidiennes (Daily)
  * 4 sauvegardes hebdomadaires (Weekly)
  * 3 sauvegardes mensuelles (Monthly)
- Notification automatique (Telegram si configuré ou journalisation)
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

# Ajout du chemin knowledge-api pour le notifier si disponible
API_DIR = Path(__file__).parent.parent / "knowledge-api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

try:
    from knowledge.services.notifier import send_admin_alert, AlertLevel
except ImportError:
    send_admin_alert = None

DEFAULT_BACKUP_DIR = Path(__file__).parent.parent / "backups"


def run_cmd(cmd: list[str], stdout_file=None) -> tuple[int, str, str]:
    """Exécute une commande système avec capture propre."""
    if stdout_file:
        res = subprocess.run(cmd, stdout=stdout_file, stderr=subprocess.PIPE, text=True)
        return res.returncode, "", res.stderr
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return res.returncode, res.stdout, res.stderr


def compute_sha256(filepath: Path) -> str:
    """Calcule le hash SHA-256 d'un fichier."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def dump_postgres(container: str, user: str, dbname: str, out_path: Path) -> bool:
    """Réalise un dump SQL propre d'une base PostgreSQL Docker."""
    print(f" -> Dump PostgreSQL [{dbname}] depuis {container}...")
    cmd = ["docker", "exec", container, "pg_dump", "-U", user, "-d", dbname, "--clean", "--if-exists"]
    with open(out_path, "w", encoding="utf-8") as f:
        rc, _, err = run_cmd(cmd, stdout_file=f)
    if rc != 0 or not out_path.exists() or out_path.stat().st_size == 0:
        print(f"[-] Erreur dump PostgreSQL {dbname}: {err}")
        return False
    size_kb = round(out_path.stat().st_size / 1024, 2)
    print(f"    [OK] {out_path.name} ({size_kb} KB)")
    return True


def dump_sqlite(container: str, db_path: str, out_path: Path) -> bool:
    """Réalise une sauvegarde cohérente SQLite via l'API .backup ou copie directe."""
    print(f" -> Sauvegarde SQLite depuis {container}:{db_path}...")
    tmp_in_container = f"/tmp/backup_{out_path.name}"
    rc, _, _ = run_cmd(["docker", "exec", container, "sqlite3", db_path, f".backup '{tmp_in_container}'"])
    if rc == 0:
        rc2, _, err2 = run_cmd(["docker", "cp", f"{container}:{tmp_in_container}", str(out_path)])
        run_cmd(["docker", "exec", container, "rm", "-f", tmp_in_container])
    else:
        # Fallback copie directe si l'utilitaire sqlite3 est absent de l'image (ex. Grafana)
        rc2, _, err2 = run_cmd(["docker", "cp", f"{container}:{db_path}", str(out_path)])

    if rc2 != 0 or not out_path.exists():
        print(f"[-] Erreur sauvegarde SQLite {container}: {err2}")
        return False
    size_kb = round(out_path.stat().st_size / 1024, 2)
    print(f"    [OK] {out_path.name} ({size_kb} KB)")
    return True


def dump_redis(container: str, out_path: Path) -> bool:
    """Force une sauvegarde BGSAVE et copie le dump.rdb."""
    print(f" -> Sauvegarde Redis RDB depuis {container}...")
    # Déclencher SAVE synchrone
    rc, _, _ = run_cmd(["docker", "exec", container, "redis-cli", "SAVE"])
    # Copier le dump.rdb
    rc2, _, err2 = run_cmd(["docker", "cp", f"{container}:/data/dump.rdb", str(out_path)])
    if rc2 != 0 or not out_path.exists():
        print(f"[-] Erreur copie Redis dump.rdb depuis {container}: {err2}")
        return False
    size_kb = round(out_path.stat().st_size / 1024, 2)
    print(f"    [OK] {out_path.name} ({size_kb} KB)")
    return True


def dump_paperless_media(container: str, out_path: Path) -> bool:
    """Archive le répertoire /usr/src/paperless/media en fluxant directement l'archive tar."""
    print(f" -> Sauvegarde Médias Paperless depuis {container}...")
    cmd = ["docker", "exec", container, "tar", "-czf", "-", "-C", "/usr/src/paperless/media", "."]
    with open(out_path, "wb") as f:
        res = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE)
    if res.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
        print(f"[-] Erreur tar média paperless: {res.stderr.decode('utf-8', errors='replace')}")
        return False
    size_kb = round(out_path.stat().st_size / 1024, 2)
    print(f"    [OK] {out_path.name} ({size_kb} KB)")
    return True


def encrypt_file(file_path: Path, password: str) -> Path:
    """Chiffre un fichier avec AES-256 (CBC + PBKDF2 HMAC SHA-256)."""
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        import secrets

        print(f"[+] Chiffrement AES-256 de {file_path.name}...")
        salt = secrets.token_bytes(16)
        iv = secrets.token_bytes(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = kdf.derive(password.encode("utf-8"))

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        encryptor = cipher.encryptor()

        with open(file_path, "rb") as f:
            data = f.read()

        # PKCS7 Padding
        pad_len = 16 - (len(data) % 16)
        data += bytes([pad_len] * pad_len)

        encrypted_data = encryptor.update(data) + encryptor.finalize()

        enc_path = file_path.with_suffix(file_path.suffix + ".enc")
        with open(enc_path, "wb") as f:
            f.write(salt + iv + encrypted_data)

        # Supprimer le fichier clair
        file_path.unlink()
        print(f"[+] Archive chiffrée avec succès : {enc_path.name}")
        return enc_path
    except Exception as e:
        print(f"[-] Échec du chiffrement AES : {e}")
        return file_path


def apply_gfs_retention(backup_dir: Path, keep_daily: int = 7, keep_weekly: int = 4, keep_monthly: int = 3):
    """
    Applique la politique de rétention GFS (Grand-père, Père, Fils) :
    - 7 sauvegardes quotidiennes (les 7 jours les plus récents)
    - 4 sauvegardes hebdomadaires (une par semaine, dimanche ou premier jour dispo)
    - 3 sauvegardes mensuelles (une par mois, 1er du mois ou premier jour dispo)
    Les archives ne correspondant à aucun des 3 paniers sont purgées.
    """
    print(f"\n[+] Application de la politique de rétention GFS dans {backup_dir.name}...")
    pattern = re.compile(r"mementomori_backup_(\d{8})_(\d{6})\.tar\.gz(?:\.enc)?$")
    archives = []

    for f in backup_dir.iterdir():
        match = pattern.match(f.name)
        if match:
            date_str = match.group(1)
            try:
                dt = datetime.datetime.strptime(date_str, "%Y%m%d")
                archives.append((dt, f))
            except ValueError:
                continue

    if not archives:
        print("  • Aucune archive éligible trouvée pour la rétention.")
        return

    # Trier par date décroissante (plus récent d'abord)
    archives.sort(key=lambda x: x[0], reverse=True)
    now = datetime.datetime.now()

    kept_files: set[Path] = set()

    # 1. Panier Quotidien (Daily) : les keep_daily archives les plus récentes
    daily_candidates = archives[:keep_daily]
    for _, path in daily_candidates:
        kept_files.add(path)

    # 2. Panier Hebdomadaire (Weekly) : 1 archive par semaine calendaire pour keep_weekly semaines
    weekly_buckets: dict[str, Path] = {}
    for dt, path in archives:
        cal_year, cal_week, _ = dt.isocalendar()
        week_key = f"{cal_year}-W{cal_week:02d}"
        if week_key not in weekly_buckets and len(weekly_buckets) < keep_weekly:
            weekly_buckets[week_key] = path
            kept_files.add(path)

    # 3. Panier Mensuel (Monthly) : 1 archive par mois pour keep_monthly mois
    monthly_buckets: dict[str, Path] = {}
    for dt, path in archives:
        month_key = dt.strftime("%Y-%m")
        if month_key not in monthly_buckets and len(monthly_buckets) < keep_monthly:
            monthly_buckets[month_key] = path
            kept_files.add(path)

    print(f"  • Archives conservées : {len(kept_files)} (Dailies: {len(daily_candidates)}, Weeklies: {len(weekly_buckets)}, Monthlies: {len(monthly_buckets)})")

    # 4. Suppression des archives expirées
    deleted_count = 0
    for dt, path in archives:
        if path not in kept_files:
            print(f"  [-] Purge de l'archive expirée : {path.name}")
            try:
                path.unlink()
                sha_file = path.with_suffix(path.suffix + ".sha256")
                if sha_file.exists():
                    sha_file.unlink()
                # Si .enc, vérifier le sha256 original
                raw_sha = Path(str(path).replace(".enc", "") + ".sha256")
                if raw_sha.exists():
                    raw_sha.unlink()
                deleted_count += 1
            except Exception as e:
                print(f"      Erreur suppression {path.name}: {e}")

    print(f"  • Fin de rétention : {deleted_count} archive(s) expirée(s) supprimée(s).")


async def run_backup(target_dir: Path, include_media: bool = True) -> bool:
    """Exécute un cycle complet de sauvegarde."""
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bundle_name = f"mementomori_backup_{timestamp}"
    archive_filename = f"{bundle_name}.tar.gz"
    final_archive_path = target_dir / archive_filename

    print("=" * 70)
    print(f"MEMENTOMORI - Sauvegarde Complète & Disaster Recovery (B1/B2)")
    print(f"Date & Heure : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Destination  : {target_dir}")
    print("=" * 70)

    # Création du dossier temporaire de staging
    staging_dir = Path(tempfile.mkdtemp(prefix=f"memento_stage_{timestamp}_"))
    try:
        manifest = {
            "backup_name": bundle_name,
            "created_at": datetime.datetime.now().isoformat(),
            "version": "1.0",
            "components": {},
        }

        # 1. PostgreSQL Knowledge DB
        f_pg_k = staging_dir / "knowledge_db.sql"
        if dump_postgres("mementomori-knowledge-db-1", "knowledge_app", "knowledge", f_pg_k):
            manifest["components"]["knowledge_db"] = {
                "file": f_pg_k.name,
                "size_bytes": f_pg_k.stat().st_size,
                "sha256": compute_sha256(f_pg_k)
            }
        else:
            raise RuntimeError("Échec sauvegarde PostgreSQL Knowledge")

        # 2. PostgreSQL Paperless DB
        f_pg_p = staging_dir / "paperless_db.sql"
        if dump_postgres("mementomori-paperless-db-1", "paperless", "paperless", f_pg_p):
            manifest["components"]["paperless_db"] = {
                "file": f_pg_p.name,
                "size_bytes": f_pg_p.stat().st_size,
                "sha256": compute_sha256(f_pg_p)
            }
        else:
            raise RuntimeError("Échec sauvegarde PostgreSQL Paperless")

        # 3. PostgreSQL Authentik DB
        f_pg_a = staging_dir / "authentik_db.sql"
        if dump_postgres("mementomori-authentik-db-1", "authentik", "authentik", f_pg_a):
            manifest["components"]["authentik_db"] = {
                "file": f_pg_a.name,
                "size_bytes": f_pg_a.stat().st_size,
                "sha256": compute_sha256(f_pg_a)
            }
        else:
            raise RuntimeError("Échec sauvegarde PostgreSQL Authentik")

        # 4. SQLite Uptime Kuma DB
        f_kuma = staging_dir / "kuma.db"
        if dump_sqlite("mementomori-uptime-kuma-1", "/app/data/kuma.db", f_kuma):
            manifest["components"]["uptime_kuma"] = {
                "file": f_kuma.name,
                "size_bytes": f_kuma.stat().st_size,
                "sha256": compute_sha256(f_kuma)
            }

        # 4b. SQLite Grafana DB
        f_grafana = staging_dir / "grafana.db"
        if dump_sqlite("mementomori-grafana-1", "/var/lib/grafana/grafana.db", f_grafana):
            manifest["components"]["grafana"] = {
                "file": f_grafana.name,
                "size_bytes": f_grafana.stat().st_size,
                "sha256": compute_sha256(f_grafana)
            }

        # 5. Redis Dumps
        f_rk = staging_dir / "knowledge_redis.rdb"
        if dump_redis("mementomori-knowledge-redis-1", f_rk):
            manifest["components"]["knowledge_redis"] = {
                "file": f_rk.name,
                "size_bytes": f_rk.stat().st_size,
                "sha256": compute_sha256(f_rk)
            }

        f_rp = staging_dir / "paperless_redis.rdb"
        if dump_redis("mementomori-paperless-redis-1", f_rp):
            manifest["components"]["paperless_redis"] = {
                "file": f_rp.name,
                "size_bytes": f_rp.stat().st_size,
                "sha256": compute_sha256(f_rp)
            }

        # 6. Paperless Media (optionnel)
        if include_media:
            f_pmedia = staging_dir / "paperless_media.tar.gz"
            if dump_paperless_media("mementomori-paperless-1", f_pmedia):
                manifest["components"]["paperless_media"] = {
                    "file": f_pmedia.name,
                    "size_bytes": f_pmedia.stat().st_size,
                    "sha256": compute_sha256(f_pmedia)
                }

        # 7. Écriture du manifest.json
        manifest_file = staging_dir / "manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        # 8. Création de l'archive tar.gz
        print(f"\n[+] Compression de l'archive consolidée : {archive_filename}...")
        with tarfile.open(final_archive_path, "w:gz") as tar:
            for item in staging_dir.iterdir():
                tar.add(item, arcname=item.name)

        archive_size_mb = round(final_archive_path.stat().st_size / (1024 * 1024), 2)
        archive_sha = compute_sha256(final_archive_path)

        # Écriture du fichier .sha256
        sha_file = target_dir / f"{archive_filename}.sha256"
        with open(sha_file, "w", encoding="utf-8") as f:
            f.write(f"{archive_sha}  {archive_filename}\n")

        print(f"[+] Archive créée ({archive_size_mb} MB) : {final_archive_path.name}")
        print(f"[+] Empreinte SHA-256 : {archive_sha}")

        # 9. Chiffrement optionnel AES si mot de passe configuré
        pwd = os.getenv("BACKUP_PASSWORD") or os.getenv("BACKUP_ENCRYPTION_KEY")
        if pwd:
            final_file = encrypt_file(final_archive_path, pwd)
        else:
            final_file = final_archive_path

        # 10. Application de la politique de rétention GFS
        apply_gfs_retention(target_dir, keep_daily=7, keep_weekly=4, keep_monthly=3)

        print("\n" + "=" * 70)
        print("RÉSULTAT : SAUVEGARDE COMPLÈTE TERMINÉE AVEC SUCCÈS (B1/B2)")
        print(f"Fichier final : {final_file.name}")
        print("=" * 70)

        # Notification proactive si disponible
        if send_admin_alert:
            await send_admin_alert(
                level="INFO",
                title="Sauvegarde Quotidienne Réussie",
                message=f"Archive {final_file.name} générée avec succès ({archive_size_mb} MB).",
                context={
                    "backup_name": bundle_name,
                    "size_mb": str(archive_size_mb),
                    "components": str(len(manifest["components"])),
                    "sha256": archive_sha[:16] + "..."
                }
            )

        return True

    except Exception as e:
        print(f"\n[-] ERREUR CRITIQUE PENDANT LA SAUVEGARDE : {e}")
        if send_admin_alert:
            await send_admin_alert(
                level="CRITICAL",
                title="Échec de la Sauvegarde Quotidienne",
                message=f"Une erreur est survenue lors du processus de sauvegarde : {e}",
                context={"stage": "backup_execution", "error": str(e)}
            )
        return False
    finally:
        # Nettoyage du staging temporaire
        shutil.rmtree(staging_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="MEMENTOMORI Backup & Disaster Recovery")
    parser.add_argument("--target-dir", type=str, default=str(DEFAULT_BACKUP_DIR), help="Dossier de stockage")
    parser.add_argument("--retention-only", action="store_true", help="Applique uniquement la rétention GFS")
    parser.add_argument("--no-media", action="store_true", help="Exclut les médias Paperless")
    args = parser.parse_args()

    target_dir = Path(args.target_dir)

    if args.retention_only:
        apply_gfs_retention(target_dir)
        sys.exit(0)

    success = asyncio.run(run_backup(target_dir, include_media=not args.no_media))
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
