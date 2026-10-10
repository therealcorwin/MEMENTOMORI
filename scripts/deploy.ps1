<#
.SYNOPSIS
    MEMENTOMORI - Script de Déploiement Sécurisé CI/CD (Exigence B2).
.DESCRIPTION
    1. Vérifications préliminaires (.env, docker, docker-compose).
    2. Sauvegarde préalable obligatoire des bases de données PostgreSQL (B1).
    3. Exécution de la suite de tests automatisés pytest (B4 Quality Gate).
    4. Construction des images Docker (API + Dashboard).
    5. Déploiement et redémarrage progressif des conteneurs.
    6. Contrôle de santé post-déploiement (/health).
#>

[CmdletBinding()]
param (
    [string]$RootDir = "D:\Dev\Python\MEMENTOMORI",
    [switch]$SkipTests = $false
)

$ErrorActionPreference = "Stop"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "         MEMENTOMORI - Déploiement Continu Automatisé (B2)           " -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

$ComposeFile = Join-Path $RootDir "docker-compose.knowledge.yml"
$BackupDir = Join-Path $RootDir "backups"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

# ------------------------------------------------------------------------------
# 1. VÉRIFICATIONS PRÉLIMINAIRES
# ------------------------------------------------------------------------------
Write-Host "`n[1/6] Vérifications préliminaires de l'environnement..." -ForegroundColor Yellow

$EnvFile = Join-Path $RootDir ".env"
if (-not (Test-Path $EnvFile)) {
    throw "Le fichier .env est introuvable à la racine ($EnvFile) !"
}
Write-Host "[+] Fichier .env présent." -ForegroundColor Green

try {
    docker info > $null 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Docker inaccessible" }
    Write-Host "[+] Moteur Docker opérationnel." -ForegroundColor Green
}
catch {
    throw "Le moteur Docker n'est pas actif ou inaccessible !"
}

if (-not (Test-Path $ComposeFile)) {
    throw "Le fichier compose ($ComposeFile) est introuvable !"
}
Write-Host "[+] Fichier compose validé." -ForegroundColor Green

# ------------------------------------------------------------------------------
# 2. SAUVEGARDE PRÉALABLE OBLIGATOIRE DES BASES DE DONNÉES (B1)
# ------------------------------------------------------------------------------
Write-Host "`n[2/6] Sauvegarde préalable des bases de données en production (B1)..." -ForegroundColor Yellow

if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

$Databases = @(
    @{ Container = "mementomori-knowledge-db-1"; User = "knowledge_app"; DB = "knowledge" },
    @{ Container = "mementomori-paperless-db-1"; User = "paperless"; DB = "paperless" },
    @{ Container = "mementomori-authentik-db-1"; User = "authentik"; DB = "authentik" }
)

foreach ($db in $Databases) {
    $cName = $db.Container
    $uName = $db.User
    $dName = $db.DB
    $outFile = Join-Path $BackupDir "${cName}_predeploy_${Timestamp}.sql"

    $isRunning = docker inspect -f '{{.State.Running}}' $cName 2>$null
    if ($isRunning -eq "true") {
        Write-Host " -> Sauvegarde de [$cName] (base: $dName)..." -NoNewline
        try {
            & docker exec $cName pg_dump -U $uName $dName > $outFile
            if ($LASTEXITCODE -eq 0 -and (Get-Item $outFile).Length -gt 0) {
                $sizeKb = [math]::Round((Get-Item $outFile).Length / 1KB, 2)
                Write-Host " [OK] ($sizeKb KB -> $(Split-Path $outFile -Leaf))" -ForegroundColor Green
            }
            else {
                Write-Host " [ÉCHEC]" -ForegroundColor Red
                if (Test-Path $outFile) { Remove-Item $outFile -Force }
                throw "Échec du dump sur $cName"
            }
        }
        catch {
            Write-Host " [ERREUR] $_" -ForegroundColor Red
            throw "Sauvegarde interrompue pour $cName. Annulation du déploiement."
        }
    }
    else {
        Write-Host " -> Conteneur [$cName] inactif, dump ignoré." -ForegroundColor DarkGray
    }
}

# ------------------------------------------------------------------------------
# 3. QUALITÉ & SUITE DE TESTS AUTOMATISÉS (B4)
# ------------------------------------------------------------------------------
Write-Host "`n[3/6] Validation de la suite de tests automatisés (Quality Gate)..." -ForegroundColor Yellow

if ($SkipTests) {
    Write-Host "[!] Tests ignorés (-SkipTests spécifié)." -ForegroundColor DarkYellow
}
else {
    Write-Host " -> Exécution de pytest dans knowledge-api..."
    Push-Location (Join-Path $RootDir "knowledge-api")
    try {
        & poetry run pytest -q --tb=short
        if ($LASTEXITCODE -ne 0) {
            throw "Échec des tests pytest. Déploiement annulé."
        }
        Write-Host "[+] Suite de tests backend validée à 100% vert." -ForegroundColor Green
    }
    finally {
        Pop-Location
    }
}

# ------------------------------------------------------------------------------
# 4. CONSTRUCTION DES IMAGES DOCKER
# ------------------------------------------------------------------------------
Write-Host "`n[4/6] Construction et mise à jour des images Docker..." -ForegroundColor Yellow
Push-Location $RootDir
try {
    docker compose -f $ComposeFile build knowledge-api knowledge-dashboard
    if ($LASTEXITCODE -ne 0) {
        throw "Échec du build des images Docker."
    }
    Write-Host "[+] Images Docker construites avec succès." -ForegroundColor Green
}
finally {
    Pop-Location
}

# ------------------------------------------------------------------------------
# 5. DÉPLOIEMENT DES CONTENEURS
# ------------------------------------------------------------------------------
Write-Host "`n[5/6] Déploiement et redémarrage des services..." -ForegroundColor Yellow
Push-Location $RootDir
try {
    docker compose -f $ComposeFile up -d --remove-orphans
    if ($LASTEXITCODE -ne 0) {
        throw "Échec du démarrage des conteneurs via docker compose."
    }
    Write-Host "[+] Conteneurs déployés en arrière-plan." -ForegroundColor Green
}
finally {
    Pop-Location
}

# ------------------------------------------------------------------------------
# 6. CONTRÔLE DE SANTÉ POST-DÉPLOIEMENT (HEALTHCHECK)
# ------------------------------------------------------------------------------
Write-Host "`n[6/6] Contrôle de santé post-déploiement..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

try {
    $healthResp = Invoke-RestMethod -Uri "http://127.0.0.1:8100/health" -Method Get -TimeoutSec 5 -ErrorAction Stop
    if ($healthResp.status -in @("ok", "healthy")) {
        Write-Host "[+] API Healthcheck : OK (status: healthy)" -ForegroundColor Green
    }
    else {
        Write-Host "[!] Avertissement : Statut de l'API : $($healthResp.status)" -ForegroundColor Yellow
    }
}
catch {
    Write-Host "[!] Impossible de joindre l'API en direct sur 127.0.0.1:8100/health : $_" -ForegroundColor Yellow
}

Write-Host "`nÉtat des conteneurs MEMENTOMORI :" -ForegroundColor Cyan
docker ps --filter "name=mementomori-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

Write-Host "`n======================================================================" -ForegroundColor Green
Write-Host "          [SUCCÈS] Déploiement MEMENTOMORI terminé avec succès !      " -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green

