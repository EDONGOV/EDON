# Read .env and set Fly secrets in one go.
# Run from repo root:  .\edon_gateway\scripts\fly_secrets_from_env.ps1
# Or from edon_gateway: .\scripts\fly_secrets_from_env.ps1

$ErrorActionPreference = "Stop"
$gatewayRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envFile = Join-Path $gatewayRoot ".env"
Push-Location $gatewayRoot
try {
if (-not (Test-Path $envFile)) {
    Write-Error ".env not found at $envFile. Create it from .env.example and run again."
}

# Parse KEY=VALUE (unquoted or quoted), skip comments/empties
$vars = @{}
Get-Content $envFile -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) { return }
    $idx = $line.IndexOf("=")
    if ($idx -le 0) { return }
    $key = $line.Substring(0, $idx).Trim()
    $val = $line.Substring($idx + 1).Trim()
    if ($val.StartsWith('"') -and $val.EndsWith('"')) { $val = $val.Substring(1, $val.Length - 2) }
    if ($val.StartsWith("'") -and $val.EndsWith("'")) { $val = $val.Substring(1, $val.Length - 2) }
    $vars[$key] = $val
}

$wanted = @(
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "CLERK_SECRET_KEY",
    "EDON_API_TOKEN",
    "EDON_DB_ENCRYPTION_KEY",
    "EDON_CORS_ORIGINS",
    "EDON_CREDENTIALS_STRICT",
    "EDON_ALLOW_ENV_TOKEN_IN_PROD"
)

$secretArgs = @()
foreach ($k in $wanted) {
    if ($vars.ContainsKey($k) -and $vars[$k] -ne "") {
        $v = $vars[$k]
        # Fly CLI: wrap in double quotes if value contains space or equals
        if ($v -match "[\s=]") { $v = "`"$v`"" }
        $secretArgs += "${k}=$v"
    }
}

if ($secretArgs.Count -eq 0) {
    Write-Error "None of the required keys found in .env. Add at least STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, CLERK_SECRET_KEY, EDON_API_TOKEN, EDON_DB_ENCRYPTION_KEY."
}

Write-Host "Setting $($secretArgs.Count) Fly secrets from .env..."
& fly secrets set @secretArgs
} finally {
    Pop-Location
}
