#!/usr/bin/env bash
# ==============================================================================
# MEMENTOMORI - Script de mise à jour sécurisée des conteneurs Docker (Exigence B1)
# ==============================================================================
set -euo pipefail

DOCKER_DIR="${1:-D:/Dev/Docker/MEMENTOMORI}"
BACKUP_DIR="${DOCKER_DIR}/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RETENTION_DAYS=7

echo "=================================================="
echo "   MEMENTOMORI - Mise à jour des conteneurs (B1)   "
echo "=================================================="

mkdir -p "$BACKUP_DIR"

# 1. Sauvegarde préalable obligatoire des bases de données
echo -e "\n[1/4] Sauvegarde préalable obligatoire des bases de données..."

declare -A DATABASES=(
    ["mementomori-knowledge-db"]="knowledge_app:knowledge"
    ["mementomori-paperless-db"]="paperless:paperless"
    ["mementomori-authentik-db"]="authentik:authentik"
)

for container in "${!DATABASES[@]}"; do
    IFS=":" read -r user db <<< "${DATABASES[$container]}"
    out_file="${BACKUP_DIR}/${container}_${TIMESTAMP}.sql"
    echo -n " -> Sauvegarde de [${container}] (base: ${db})... "

    if ! docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        echo "[ERREUR]"
        echo "Le conteneur ${container} n'est pas actif ! Annulation de la mise à jour."
        exit 1
    fi

    if docker exec "$container" pg_dump -U "$user" "$db" > "$out_file" && [ -s "$out_file" ]; then
        size=$(du -h "$out_file" | cut -f1)
        echo "[OK] (${size} -> $(basename "$out_file"))"
    else
        echo "[ÉCHEC]"
        rm -f "$out_file"
        echo "Échec critique du dump pour ${container}. Annulation immédiate de la mise à jour."
        exit 1
    fi
done

# Nettoyage vieux backups
find "$BACKUP_DIR" -name "*.sql" -mtime +$RETENTION_DAYS -delete || true

# 2. Pull
echo -e "\n[2/4] Téléchargement des nouvelles images Docker..."
cd "$DOCKER_DIR"
docker compose pull

# 3. Up
echo -e "\n[3/4] Redémarrage et mise à jour des conteneurs..."
docker compose up -d --remove-orphans

# 4. Statut
echo -e "\n[4/4] Contrôle de l'état des conteneurs..."
sleep 5
docker ps --filter "name=mementomori-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo -e "\n[SUCCÈS] Mise à jour terminée avec succès et sauvegardes validées."
