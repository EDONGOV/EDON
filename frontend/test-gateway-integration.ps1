# Test script for Agent UI - Gateway Integration
# This script tests the agent UI against a running EDON Gateway

Write-Host "Testing EDON Agent UI - Gateway Integration" -ForegroundColor Green
Write-Host ""

# Check if gateway is running
$gatewayUrl = "http://localhost:8000"
Write-Host "Checking if gateway is running at $gatewayUrl..." -ForegroundColor Yellow

try {
    $healthCheck = Invoke-WebRequest -Uri "$gatewayUrl/healthz" -Method GET -TimeoutSec 5 -ErrorAction Stop
    if ($healthCheck.StatusCode -eq 200) {
        Write-Host "✓ Gateway is running" -ForegroundColor Green
    } else {
        Write-Host "✗ Gateway returned status code: $($healthCheck.StatusCode)" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "✗ Gateway is not running at $gatewayUrl" -ForegroundColor Red
    Write-Host "  Please start the gateway first:" -ForegroundColor Yellow
    Write-Host "  cd C:\Users\cjbig\Desktop\EDON\edon-cav-engine\edon_gateway" -ForegroundColor Gray
    Write-Host "  python -m edon_gateway.main" -ForegroundColor Gray
    exit 1
}

Write-Host ""
Write-Host "Running integration tests..." -ForegroundColor Yellow
Write-Host ""

# Set environment variables for tests
$env:VITE_EDON_GATEWAY_URL = $gatewayUrl
$env:VITE_EDON_GATEWAY_TOKEN = ""  # Add token if auth is enabled

# Run tests
cd C:\Users\cjbig\Desktop\edon-agent-ui
npm test

Write-Host ""
Write-Host "Tests completed!" -ForegroundColor Green
