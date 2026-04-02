# Start EDON Gateway in Production Mode
# This script sets production environment variables and starts the gateway

Write-Host "Starting EDON Gateway in Production Mode..." -ForegroundColor Cyan
Write-Host ""

# Set production environment variables
$env:EDON_CREDENTIALS_STRICT = "true"
$env:EDON_VALIDATE_STRICT = "true"
$env:EDON_AUTH_ENABLED = "true"
$env:EDON_API_TOKEN = if ($env:EDON_API_TOKEN) { $env:EDON_API_TOKEN } else { "production-token-change-me" }

Write-Host "Production Configuration:" -ForegroundColor Yellow
Write-Host "  EDON_CREDENTIALS_STRICT=$env:EDON_CREDENTIALS_STRICT"
Write-Host "  EDON_VALIDATE_STRICT=$env:EDON_VALIDATE_STRICT"
Write-Host "  EDON_AUTH_ENABLED=$env:EDON_AUTH_ENABLED"
Write-Host "  EDON_API_TOKEN=$env:EDON_API_TOKEN"
Write-Host ""

Write-Host "Starting gateway server..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

# Start the gateway
python -m uvicorn edon_gateway.main:app --host 0.0.0.0 --port 8000
