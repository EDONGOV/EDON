param(
    [string]$GatewayUrl = $env:EDON_GATEWAY_URL,
    [string]$ApiToken   = $env:EDON_API_TOKEN
)

if (-not $GatewayUrl) { $GatewayUrl = "http://127.0.0.1:8000" }
if (-not $ApiToken)   { throw "EDON_API_TOKEN is required" }

$headers = @{
    "Content-Type" = "application/json"
    "X-EDON-TOKEN" = $ApiToken
}
if ($env:EDON_TENANT_ID) { $headers["X-Tenant-ID"] = $env:EDON_TENANT_ID }

Write-Host "== EDON production readiness (one click) =="
Write-Host "Gateway: $GatewayUrl"

function Check-Endpoint {
    param([string]$Path)
    try {
        $resp = Invoke-RestMethod -Method Get -Uri "$GatewayUrl$Path" -Headers $headers
        Write-Host "[OK] $Path"
    } catch {
        Write-Host "[WARN] $Path failed: $($_.Exception.Message)"
    }
}

Check-Endpoint "/health"
Check-Endpoint "/docs"
Check-Endpoint "/metrics"

# Optional: connect Clawdbot integration if env vars present
if ($env:CLAWDBOT_GATEWAY_URL -and $env:CLAWDBOT_GATEWAY_TOKEN) {
    $body = @{
        base_url     = $env:CLAWDBOT_GATEWAY_URL
        auth_mode    = "token"
        secret       = $env:CLAWDBOT_GATEWAY_TOKEN
        credential_id= $(if ($env:EDON_CLAWDBOT_CREDENTIAL_ID) { $env:EDON_CLAWDBOT_CREDENTIAL_ID } else { "clawdbot_gateway" })
        probe        = $false
    } | ConvertTo-Json -Depth 4
    try {
        Invoke-RestMethod -Method Post -Uri "$GatewayUrl/integrations/clawdbot/connect" -Headers $headers -Body $body | Out-Null
        Write-Host "[OK] Clawdbot integration connected"
    } catch {
        Write-Host "[WARN] Clawdbot connect failed: $($_.Exception.Message)"
    }
}

# Run regression tests
Write-Host "Running regression tests..."
$env:EDON_GATEWAY_URL = $GatewayUrl
$env:EDON_AUTH_ENABLED = "true"
$env:EDON_API_TOKEN = $ApiToken
python "test_regression.py"
