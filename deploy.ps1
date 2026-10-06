param (
    [switch]$SkipTests = $false
)
& "$PSScriptRoot\scripts\deploy.ps1" -SkipTests:$SkipTests

