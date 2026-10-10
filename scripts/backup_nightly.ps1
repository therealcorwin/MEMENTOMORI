<#
.SYNOPSIS
    MEMENTOMORI - Script d'automatisation des Sauvegardes Quotidiennes & Planificateur Windows (B1/B2).
.DESCRIPTION
    1. Exécute la sauvegarde consolidée GFS via scripts/backup.py.
    2. Enregistre une Tâche Planifiée Windows (Scheduled Task) quotidienne à 03h00 via schtasks.
.PARAMETER RegisterTask
    Enregistre la tâche planifiée sous Windows pour une exécution quotidienne automatique à 03h00.
.PARAMETER UnregisterTask
    Supprime la tâche planifiée Windows existante.
.PARAMETER TargetDir
    Chemin cible pour le stockage des archives déportées (ex. NAS, disque externe).
.PARAMETER NoMedia
    Exclut l'archivage des médias volumineux.
#>

[CmdletBinding()]
param (
    [switch]$RegisterTask = $false,
    [switch]$UnregisterTask = $false,
    [string]$TargetDir = "",
    [switch]$NoMedia = $false,
    [string]$ScheduleTime = "03:00"
)

$RootDir = "D:\Dev\Python\MEMENTOMORI"
$TaskName = "MEMENTOMORI_Backup_Nightly"
$PythonExe = Join-Path $RootDir ".venv\Scripts\python.exe"
$BackupScript = Join-Path $RootDir "scripts\backup.py"

# --- 1. DÉSENREGISTREMENT DE LA TÂCHE ---
if ($UnregisterTask) {
    Write-Host "[+] Suppression de la tâche planifiée '$TaskName'..." -ForegroundColor Yellow
    & schtasks /delete /tn $TaskName /f
    Write-Host "[OK] Tâche '$TaskName' supprimée." -ForegroundColor Green
    exit 0
}

# --- 2. ENREGISTREMENT DE LA TÂCHE PLANIFIÉE WINDOWS ---
if ($RegisterTask) {
    Write-Host "======================================================================" -ForegroundColor Cyan
    Write-Host " Enregistrement de la Tâche Planifiée Windows : $TaskName             " -ForegroundColor Cyan
    Write-Host "======================================================================" -ForegroundColor Cyan

    $taskRun = "`"$PythonExe`" `"$BackupScript`""
    if ($TargetDir) {
        $taskRun += " --target-dir `"$TargetDir`""
    }
    if ($NoMedia) {
        $taskRun += " --no-media"
    }

    $res = & schtasks /create /tn $TaskName /tr $taskRun /sc daily /st $ScheduleTime /f
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[+] Tâche planifiée '$TaskName' enregistrée avec succès !" -ForegroundColor Green
        Write-Host "    Heure d'exécution : Tous les jours à $ScheduleTime" -ForegroundColor Cyan
        Write-Host "    Commande          : $taskRun" -ForegroundColor Cyan
    }
    else {
        Write-Host "[-] Échec de l'enregistrement de la tâche planifiée (Code: $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    exit 0
}

# --- 3. EXÉCUTION DIRECTE DE LA SAUVEGARDE ---
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host " MEMENTOMORI - Lancement de la Sauvegarde Déportée                     " -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

$pyArgs = @($BackupScript)
if ($TargetDir) {
    $pyArgs += "--target-dir"
    $pyArgs += $TargetDir
}
if ($NoMedia) {
    $pyArgs += "--no-media"
}

& $PythonExe @pyArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "[-] Échec lors de la sauvegarde (code: $LASTEXITCODE)" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "`n[+] Sauvegarde déportée terminée avec succès." -ForegroundColor Green

