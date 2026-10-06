<#
.SYNOPSIS
    Applique un palier de version Authentik, lance les conteneurs et attend la validation.
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$Version,
    [string]$ComposePath = "D:\Dev\Docker\MEMENTOMORI\docker-compose.yml"
)

$content = Get-Content $ComposePath -Raw
$newContent = [regex]::Replace($content, 'image: ghcr\.io/goauthentik/server:[0-9\.]+', "image: ghcr.io/goauthentik/server:$Version")
Set-Content -Path $ComposePath -Value $newContent -Encoding UTF8

Write-Host "docker-compose.yml mis à jour vers $Version" -ForegroundColor Cyan
Push-Location (Split-Path $ComposePath)
try {
    docker compose up -d authentik-server authentik-worker
    Write-Host "Attente de l'application des migrations..." -ForegroundColor Yellow
    $retries = 30
    $success = $false
    while ($retries -gt 0) {
        Start-Sleep -Seconds 4
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:9000/-/health/live/" -Method Get -TimeoutSec 3 -UseBasicParsing 2>$null
            if ($resp.StatusCode -eq 200) {
                $success = $true
                break
            }
        } catch {}
        $retries--
    }
    if ($success) {
        Write-Host "Succès : Authentik $Version est en ligne et sain !" -ForegroundColor Green
    } else {
        Write-Error "Authentik $Version n'a pas répondu dans le délai imparti."
    }
} finally {
    Pop-Location
}

