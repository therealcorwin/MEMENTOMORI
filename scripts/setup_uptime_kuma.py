"""
Script de configuration automatisée des sondes Uptime Kuma 2.x (Sprint 10, Tâche 10.4).
Configure les sondes HTTP internes pour l'ensemble des composants clés de MEMENTOMORI :
- knowledge-api (http://knowledge-api:8100/health)
- authentik (http://authentik-server:9000/-/health/live/)
- paperless (http://paperless:8000/api/)
- grafana (http://grafana:3000/api/health)
- dashboard (http://knowledge-dashboard:80/)
- traefik (http://traefik:9002/ping)
- prometheus (http://prometheus:9090/-/healthy)
- loki (http://loki:3100/ready)

Et configure le canal d'alerte Telegram si les identifiants sont fournis dans .env ou en CLI.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

CONTAINER_NAME = "mementomori-uptime-kuma-1"
DB_PATH = "/app/data/kuma.db"

MONITORS = [
    {
        "name": "knowledge-api",
        "url": "http://knowledge-api:8100/health",
        "interval": 60,
        "retry_interval": 30,
        "maxretries": 2,
    },
    {
        "name": "authentik",
        "url": "http://authentik-server:9000/-/health/live/",
        "interval": 60,
        "retry_interval": 30,
        "maxretries": 2,
    },
    {
        "name": "paperless",
        "url": "http://paperless:8000/api/",
        "interval": 60,
        "retry_interval": 30,
        "maxretries": 2,
    },
    {
        "name": "grafana",
        "url": "http://grafana:3000/api/health",
        "interval": 60,
        "retry_interval": 30,
        "maxretries": 2,
    },
    {
        "name": "knowledge-dashboard",
        "url": "http://knowledge-dashboard:80/",
        "interval": 60,
        "retry_interval": 30,
        "maxretries": 2,
    },
    {
        "name": "traefik",
        "url": "http://traefik:9002/ping",
        "interval": 60,
        "retry_interval": 30,
        "maxretries": 2,
    },
    {
        "name": "prometheus",
        "url": "http://prometheus:9090/-/healthy",
        "interval": 60,
        "retry_interval": 30,
        "maxretries": 2,
    },
    {
        "name": "loki",
        "url": "http://loki:3100/ready",
        "interval": 60,
        "retry_interval": 30,
        "maxretries": 2,
    },
]


def exec_docker_sqlite(query: str) -> str:
    """Exécute une requête SQL dans le conteneur Uptime Kuma SQLite."""
    cmd = ["docker", "exec", "-i", CONTAINER_NAME, "sqlite3", DB_PATH, query]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        raise RuntimeError(f"Erreur SQLite ({res.returncode}): {res.stderr}")
    return res.stdout.strip()


def get_first_user_id() -> int:
    """Récupère l'ID du premier utilisateur configuré dans Uptime Kuma."""
    out = exec_docker_sqlite("SELECT id FROM user ORDER BY id ASC LIMIT 1;")
    if out:
        return int(out.splitlines()[0].strip())
    return 1


def sync_monitors(user_id: int):
    """Insère ou met à jour les sondes dans la base Uptime Kuma."""
    print("[+] Synchronisation des sondes de supervision...")
    for mon in MONITORS:
        name = mon["name"]
        url = mon["url"]
        interval = mon["interval"]
        retry_interval = mon["retry_interval"]
        maxretries = mon["maxretries"]

        # Vérifier si la sonde existe déjà par URL ou nom
        check_q = f"SELECT id, name, url FROM monitor WHERE name = '{name}' OR url = '{url}';"
        existing = exec_docker_sqlite(check_q)

        if existing:
            mon_id = existing.split("|")[0]
            print(f"  • Sonde existante [{mon_id}] {name} -> mise à jour...")
            update_q = f"""
            UPDATE monitor
            SET active = 1,
                interval = {interval},
                retry_interval = {retry_interval},
                maxretries = {maxretries},
                url = '{url}'
            WHERE id = {mon_id};
            """
            exec_docker_sqlite(update_q)
        else:
            print(f"  • Nouvelle sonde : {name} ({url}) -> création...")
            insert_q = f"""
            INSERT INTO monitor (
                name, active, user_id, interval, url, type, weight, created_date,
                maxretries, ignore_tls, upside_down, maxredirects, accepted_statuscodes_json,
                dns_resolve_type, retry_interval, method, expiry_notification,
                grpc_enable_tls, resend_interval, packet_size, http_body_encoding,
                invert_keyword, json_path, timeout, gamedig_given_port_only, kafka_producer_ssl,
                kafka_producer_allow_auto_topic_creation, mqtt_check_type, snmp_version,
                json_path_operator, cache_bust, conditions, rabbitmq_nodes, ws_ignore_sec_websocket_accept_header,
                ws_subprotocol, ping_count, ping_numeric, ping_per_request_timeout,
                domain_expiry_notification, save_response, save_error_response, response_max_length,
                location, retry_only_on_status_code_failure, screenshot_delay, ntp_stratum_threshold,
                ntp_time_offset_threshold, ntp_root_dispersion_threshold, ssh_auth_method
            ) VALUES (
                '{name}', 1, {user_id}, {interval}, '{url}', 'http', 2000, DATETIME('now'),
                {maxretries}, 0, 0, 10, '["200-299"]',
                'A', {retry_interval}, 'GET', 1,
                0, 0, 56, 'json',
                0, '$', 48.0, 1, 0,
                0, 'keyword', '2c',
                '==', 0, '[]', '[]', 0,
                '', 3, 1, 2,
                1, 0, 1, 1024,
                'world', 0, 0, 5,
                1000, 500, 'password'
            );
            """
            exec_docker_sqlite(insert_q)


def sync_telegram_notification(user_id: int):
    """Configure la notification Telegram si les variables d'environnement sont présentes."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_ADMIN_CHAT_ID") or os.getenv("ADMIN_CHAT_ID") or os.getenv("COPRO_CHAT_ID")

    if not bot_token or not chat_id:
        print("[!] Telegram : aucun token BOT ou CHAT_ID renseigné dans .env. Canal d'alerte en attente.")
        return

    print(f"[+] Configuration du canal d'alerte Telegram administrateur (Chat ID: {chat_id})...")
    config_data = {
        "type": "telegram",
        "telegramBotToken": bot_token,
        "telegramChatID": str(chat_id),
        "telegramSendSilently": False,
        "telegramProtectContent": False
    }
    config_json = json.dumps(config_data).replace("'", "''")

    notif_check = exec_docker_sqlite("SELECT id FROM notification WHERE name = 'Telegram Admin Alert';")
    if notif_check:
        notif_id = notif_check.splitlines()[0].strip()
        print(f"  • Mise à jour notification Telegram existante ID [{notif_id}]...")
        exec_docker_sqlite(f"UPDATE notification SET config = '{config_json}', active = 1, is_default = 1 WHERE id = {notif_id};")
    else:
        print("  • Création du canal de notification Telegram...")
        insert_n = f"""
        INSERT INTO notification (name, active, user_id, is_default, config)
        VALUES ('Telegram Admin Alert', 1, {user_id}, 1, '{config_json}');
        """
        exec_docker_sqlite(insert_n)
        notif_id = exec_docker_sqlite("SELECT id FROM notification WHERE name = 'Telegram Admin Alert';").strip()

    # Lier le canal à toutes les sondes existantes
    print("  • Association du canal Telegram à l'ensemble des sondes...")
    all_monitors = exec_docker_sqlite("SELECT id FROM monitor;").splitlines()
    for m in all_monitors:
        m_id = m.strip()
        if not m_id:
            continue
        link_check = exec_docker_sqlite(f"SELECT id FROM monitor_notification WHERE monitor_id = {m_id} AND notification_id = {notif_id};")
        if not link_check:
            exec_docker_sqlite(f"INSERT INTO monitor_notification (monitor_id, notification_id) VALUES ({m_id}, {notif_id});")


def restart_and_verify():
    """Redémarre le conteneur Uptime Kuma et contrôle l'exécution des sondes."""
    print("[+] Redémarrage de Uptime Kuma pour prise en compte immédiate...")
    subprocess.run(["docker", "restart", CONTAINER_NAME], check=True, capture_output=True)
    print("[+] En attente de démarrage du conteneur (8 secondes)...")
    time.sleep(8)

    print("\n--- Liste des Sondes Actives dans Uptime Kuma ---")
    monitors_list = exec_docker_sqlite("SELECT id, name, type, url, active FROM monitor;")
    for line in monitors_list.splitlines():
        if line.strip():
            parts = line.split("|")
            status_txt = "ACTIF" if parts[4] == "1" else "INACTIF"
            print(f" • ID {parts[0]:<2} | {parts[1]:<20} | {parts[2]:<6} | {status_txt:<7} | {parts[3]}")

    print("\n[+] Vérification des premiers battements de cœur (Heartbeats) après 15 secondes...")
    time.sleep(15)
    hb_list = exec_docker_sqlite("SELECT m.name, h.status, h.msg, h.time FROM heartbeat h JOIN monitor m ON h.monitor_id = m.id WHERE h.id IN (SELECT MAX(id) FROM heartbeat GROUP BY monitor_id);")
    print("--- Statut en temps réel des sondes ---")
    all_up = True
    for line in hb_list.splitlines():
        if line.strip():
            parts = line.split("|")
            st = "UP (200)" if parts[1] == "1" else "DOWN"
            if parts[1] != "1":
                all_up = False
            print(f" • {parts[0]:<20} : {st:<10} ({parts[2]}) - {parts[3]}")

    if all_up:
        print("\n[SUCCÈS] Toutes les sondes Uptime Kuma sont opérationnelles et au vert !")
    else:
        print("\n[ATTENTION] Certaines sondes signalent une anomalie.")


def main():
    print("=" * 70)
    print("MEMENTOMORI - Configuration Uptime Kuma 2.x & Alerting (Sprint 10, Tâche 10.4)")
    print("=" * 70)
    user_id = get_first_user_id()
    print(f"[+] Utilisateur Uptime Kuma détecté (ID: {user_id})")
    sync_monitors(user_id)
    sync_telegram_notification(user_id)
    restart_and_verify()


if __name__ == "__main__":
    main()

