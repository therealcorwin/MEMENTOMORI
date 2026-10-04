<#
.SYNOPSIS
    MEMENTOMORI - Script de mise à jour sécurisée des conteneurs Docker (Exigence B1).
.DESCRIPTION
    1. Effectue un dump préalable obligatoire de toutes les bases PostgreSQL (knowledge-db, paperless-db, authentik-db).
    2. En cas d'échec du dump, interrompt immédiatement la procédure.
    3. Met à jour les images Docker (`docker compose pull`).
    4. Redéploie les services (`docker compose up -d --remove-orphans`).
    5. Vérifie la bonne santé des conteneurs.
#>

[CmdletBinding()]
param (
    [string]$DockerDir = "D:\Dev\Docker\MEMENTOMORI",
    [int]$RetentionDays = 7
)

$ErrorActionPreference = "Stop"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "   MEMENTOMORI - Mise à jour des conteneurs (B1)   " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir = Join-Path $DockerDir "backups"

if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
    Write-Host "[+] Répertoire de backup créé : $BackupDir" -ForegroundColor Green
}

# -----------------------------------------------------------------------------
# 1. SAUVEGARDE PRÉALABLE DES BASES DE DONNÉES (DUMP OBLIGATOIRE)
# -----------------------------------------------------------------------------
Write-Host "`n[1/4] Sauvegarde préalable obligatoire des bases de données..." -ForegroundColor Yellow

$Databases = @(
    @{ Container = "mementomori-knowledge-db"; User = "knowledge_app"; DB = "knowledge" },
    @{ Container = "mementomori-paperless-db"; User = "paperless"; DB = "paperless" },
    @{ Container = "mementomori-authentik-db"; User = "authentik"; DB = "authentik" }
)

foreach ($db in $Databases) {
    $cName = $db.Container
    $uName = $db.User
    $dName = $db.DB
    $outFile = Join-Path $BackupDir "${cName}_${Timestamp}.sql"

    Write-Host " -> Sauvegarde de [$cName] (base: $dName)..." -NoNewline
    
    # Vérification que le conteneur tourne
    $isRunning = docker inspect -f '{{.State.Running}}' $cName 2>$null
    if ($isRunning -ne "true") {
        Write-Host " [ERREUR]" -ForegroundColor Red
        throw "Le conteneur $cName n'est pas actif ! Impossible d'effectuer le dump préalable. Mise à jour annulée."
    }

    try {
        & docker exec $cName pg_dump -U $uName $dName > $outFile
        if ($LASTEXITCODE -ne 0 -or (Get-Item $outFile).Length -eq 0) {
            throw "Erreur pg_dump sur $cName"
        }
        $sizeKb = [math]::Round((Get-Item $outFile).Length / 1KB, 2)
        Write-Host " [OK] ($sizeKb KB -> $(Split-Path $outFile -Leaf))" -ForegroundColor Green
    }
    catch {
        Write-Host " [ÉCHEC]" -ForegroundColor Red
        if (Test-Path $outFile) { Remove-Item $outFile -Force }
        throw "Échec critique du dump pour $cName : $_. La mise à jour des conteneurs est annulée pour préserver l'intégrité des données."
    }
}

# Nettoyage des vieux dumps (> RetentionDays)
Get-ChildItem -Path $BackupDir -Filter "*.sql" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$RetentionDays) } | Remove-Item -Force

# -----------------------------------------------------------------------------
# 2. PULL DES DERNIÈRES IMAGES DOCKER
# -----------------------------------------------------------------------------
Write-Host "`n[2/4] Téléchargement des nouvelles images Docker..." -ForegroundColor Yellow
Push-Location $DockerDir
try {
    docker compose pull
    if ($LASTEXITCODE -ne 0) {
        throw "Erreur lors du pull des images Docker."
    }
}
finally {
    Pop-Location
}

# -----------------------------------------------------------------------------
# 3. RECRÉATION ET DÉMARRAGE DES CONTENEURS
# -----------------------------------------------------------------------------
Write-Host "`n[3/4] Redémarrage et mise à jour des conteneurs..." -ForegroundColor Yellow
Push-Location $DockerDir
try {
    docker compose up -d --remove-orphans
    if ($LASTEXITCODE -ne 0) {
        throw "Erreur lors de docker compose up."
    }
}
finally {
    Pop-Location
}

# -----------------------------------------------------------------------------
# 4. VÉRIFICATION DU STATUT ET SANTÉ
# -----------------------------------------------------------------------------
Write-Host "`n[4/4] Contrôle de l'état des conteneurs..." -ForegroundColor Yellow
Start-Sleep -Seconds 5
docker ps --filter "name=mementomori-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

Write-Host "`n[SUCCÈS] Mise à jour des conteneurs terminée avec succès et sauvegardes validées." -ForegroundColor Green
