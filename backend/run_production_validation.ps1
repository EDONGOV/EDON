# Production Mode Validation Script (PowerShell)
# Validates all three security invariants end-to-end

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "EDON Gateway Production Mode Validation" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Configuration
$GATEWAY_URL = if ($env:EDON_GATEWAY_URL) { $env:EDON_GATEWAY_URL } else { "http://localhost:8000" }
$AUTH_TOKEN = if ($env:EDON_API_TOKEN) { $env:EDON_API_TOKEN } else { "test-token" }

# Check if server is running
Write-Host "Checking if gateway is running at $GATEWAY_URL..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$GATEWAY_URL/health" -Method GET -UseBasicParsing -ErrorAction Stop
    Write-Host "✓ Gateway is running" -ForegroundColor Green
} catch {
    Write-Host "❌ ERROR: Gateway not running at $GATEWAY_URL" -ForegroundColor Red
    Write-Host "   Start the gateway first: python -m uvicorn edon_gateway.main:app" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

# Set production mode environment variables
$env:EDON_CREDENTIALS_STRICT = "true"
$env:EDON_VALIDATE_STRICT = "true"
$env:EDON_AUTH_ENABLED = "true"
$env:EDON_API_TOKEN = $AUTH_TOKEN

Write-Host "Production Mode Configuration:" -ForegroundColor Cyan
Write-Host "  EDON_CREDENTIALS_STRICT=true"
Write-Host "  EDON_VALIDATE_STRICT=true"
Write-Host "  EDON_AUTH_ENABLED=true"
Write-Host ""

# Note: The server needs to be restarted with these env vars
Write-Host "⚠️  NOTE: Server must be restarted with production env vars for full validation" -ForegroundColor Yellow
Write-Host ""

# Run Python tests
Write-Host "Running production mode tests..." -ForegroundColor Cyan
python edon_gateway/test_production_mode.py

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Validation Complete" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
