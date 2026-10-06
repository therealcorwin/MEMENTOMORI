<#
.SYNOPSIS
    Script d'exécution et de suivi de la montée de version séquentielle d'Authentik.
.DESCRIPTION
    Applique les migrations schéma par schéma de 2025.2 vers 2026.8.3.
#>

[CmdletBinding()]
param (
    [string]$TargetVersion = "2026.8.3",
    [string]$DockerComposeDir = "D:\Dev\Docker\MEMENTOMORI"
)

$Versions = @(
    "2025.4.3",
    "2025.6.3",
    "2025.8.4",
    "2025.10.4",
    "2025.12.6",
    "2026.2.7",
    "2026.5.7",
    "2026.8.3"
)

Write-Host "Séquence de montée de version programmée : $($Versions -join ' -> ')" -ForegroundColor Cyan

