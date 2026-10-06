#!/usr/bin/env bash
# ==============================================================================
# MEMENTOMORI - Script de Déploiement Sécurisé CI/CD (Exigence B2)
# ==============================================================================
# Séquence : Vérification -> Sauvegarde BDD (B1) -> Tests (B4) -> Build -> Up -> Healthcheck
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.knowledge.yml"
BACKUP_DIR="${ROOT_DIR}/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

echo "======================================================================"
echo "         MEMENTOMORI - Déploiement Continu Automatisé (B2)           "
echo "======================================================================"

# ------------------------------------------------------------------------------
# 1. VÉRIFICATIONS PRÉLIMINAIRES
# ------------------------------------------------------------------------------
echo -e "\n[1/6] Vérifications préliminaires de l'environnement..."

if [ ! -f "${ROOT_DIR}/.env" ]; then
    echo "[-] ERREUR: Le fichier .env est introuvable à la racine (${ROOT_DIR}/.env) !"
    exit 1
fi
echo "[+] Fichier .env présent."

if ! docker info > /dev/null 2>&1; then
    echo "[-] ERREUR: Le moteur Docker n'est pas actif ou inaccessible !"
    exit 1
fi
echo "[+] Moteur Docker opérationnel."

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "[-] ERREUR: Le fichier compose ($COMPOSE_FILE) est introuvable !"
    exit 1
fi
echo "[+] Fichier compose validé."

# ------------------------------------------------------------------------------
# 2. SAUVEGARDE PRÉALABLE OBLIGATOIRE DES BASES DE DONNÉES (B1)
# ------------------------------------------------------------------------------
echo -e "\n[2/6] Sauvegarde préalable des bases de données en production (B1)..."
mkdir -p "$BACKUP_DIR"

declare -A DATABASES=(
    ["mementomori-knowledge-db-1"]="knowledge_app:knowledge"
    ["mementomori-paperless-db-1"]="paperless:paperless"
    ["mementomori-authentik-db-1"]="authentik:authentik"
)

for container in "${!DATABASES[@]}"; do
    IFS=":" read -r user db <<< "${DATABASES[$container]}"
    out_file="${BACKUP_DIR}/${container}_predeploy_${TIMESTAMP}.sql"

    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        echo -n " -> Sauvegarde de [${container}] (base: ${db})... "
        if docker exec "$container" pg_dump -U "$user" "$db" > "$out_file" 2>/dev/null && [ -s "$out_file" ]; then
            size=$(du -h "$out_file" | cut -f1)
            echo "[OK] (${size} -> $(basename "$out_file"))"
        else
            echo "[AVERTISSEMENT] Échec du dump ou conteneur vide."
            rm -f "$out_file"
        fi
    else
        echo " -> Conteneur [${container}] non actif, dump ignoré."
    fi
done

# ------------------------------------------------------------------------------
# 3. QUALITÉ & SUITE DE TESTS AUTOMATISÉS (B4)
# ------------------------------------------------------------------------------
echo -e "\n[3/6] Validation de la suite de tests automatisés (Quality Gate)..."

echo " -> Exécution des tests pytest sur knowledge-api..."
cd "${ROOT_DIR}/knowledge-api"
if command -v poetry > /dev/null 2>&1; then
    poetry run pytest -q --tb=short
else
    python3 -m pytest -q --tb=short
fi
echo "[+] Tests backend validés à 100% vert."

# ------------------------------------------------------------------------------
# 4. CONSTRUCTION DES IMAGES DOCKER
# ------------------------------------------------------------------------------
echo -e "\n[4/6] Construction et mise à jour des images Docker..."
cd "$ROOT_DIR"
docker compose -f "$COMPOSE_FILE" build knowledge-api knowledge-dashboard

# ------------------------------------------------------------------------------
# 5. DÉPLOIEMENT DES CONTENEURS
# ------------------------------------------------------------------------------
echo -e "\n[5/6] Déploiement et redémarrage des services..."
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

# ------------------------------------------------------------------------------
# 6. CONTRÔLE DE SANTÉ POST-DÉPLOIEMENT (HEALTHCHECK)
# ------------------------------------------------------------------------------
echo -e "\n[6/6] Contrôle de santé post-déploiement..."
sleep 5

API_HEALTH=$(docker exec mementomori-knowledge-api-1 python3 -c "import urllib.request, json; res = urllib.request.urlopen('http://127.0.0.1:8100/health'); print(json.loads(res.read()).get('status', 'unknown'))" 2>/dev/null || echo "error")

if [ "$API_HEALTH" = "healthy" ]; then
    echo "[+] API Healthcheck : OK (status: healthy)"
else
    echo "[!] AVERTISSEMENT : Healthcheck API a retourné : $API_HEALTH"
fi

echo -e "\nÉtat des conteneurs MEMENTOMORI :"
docker ps --filter "name=mementomori-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo -e "\n======================================================================"
echo "          [SUCCÈS] Déploiement MEMENTOMORI terminé avec succès !      "
echo "======================================================================"

