# Set Clawdbot Gateway credentials in EDON Gateway database
# This stores credentials securely in the database (recommended for production)

param(
    [string]$EDON_URL = "http://localhost:8000",
    [string]$EDON_TOKEN = "NEW_GATEWAY_TOKEN_12345",
    [string]$CLAWDBOT_GATEWAY_URL = "http://127.0.0.1:18789",
    [string]$CLAWDBOT_GATEWAY_TOKEN = ""
)

Write-Host "Setting Clawdbot Gateway credentials in EDON..." -ForegroundColor Cyan
Write-Host ""

# Check if Clawdbot token is provided
if (-not $CLAWDBOT_GATEWAY_TOKEN) {
    Write-Host "⚠️  CLAWDBOT_GATEWAY_TOKEN not provided!" -ForegroundColor Yellow
    Write-Host "   Please provide your Clawdbot Gateway token:" -ForegroundColor Yellow
    Write-Host "   .\set_clawdbot_credentials.ps1 -CLAWDBOT_GATEWAY_TOKEN 'your-token-here'" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

# Check if EDON token is default
if ($EDON_TOKEN -eq "NEW_GATEWAY_TOKEN_12345") {
    Write-Host "⚠️  Using placeholder EDON token. Update -EDON_TOKEN if different." -ForegroundColor Yellow
    Write-Host ""
}

try {
    $headers = @{
        "X-EDON-TOKEN" = $EDON_TOKEN
        "Content-Type" = "application/json"
    }
    
    # Correct schema for /credentials/set:
    # credential_data should have "base_url" and "token"
    $body = @{
        credential_id   = "clawdbot_gateway"
        tool_name       = "clawdbot"  # Must match tool name used by connector
        credential_type = "gateway"    # Type identifier
        credential_data = @{
            base_url   = $CLAWDBOT_GATEWAY_URL
            token      = $CLAWDBOT_GATEWAY_TOKEN
        }
        encrypted       = $true
    }
    
    Write-Host "Sending request to: $EDON_URL/credentials/set" -ForegroundColor Gray
    Write-Host "Credential ID: clawdbot_gateway" -ForegroundColor Gray
    Write-Host "Tool Name: clawdbot" -ForegroundColor Gray
    Write-Host "Schema: base_url + token" -ForegroundColor Gray
    Write-Host ""
    
    $response = Invoke-RestMethod -Method Post -Uri "$EDON_URL/credentials/set" `
        -Headers $headers `
        -Body ($body | ConvertTo-Json -Depth 10) `
        -ErrorAction Stop
    
    Write-Host "✅ Credentials saved successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Response:" -ForegroundColor Cyan
    Write-Host "  Credential ID: $($response.credential_id)" -ForegroundColor White
    Write-Host "  Tool Name: $($response.tool_name)" -ForegroundColor White
    Write-Host "  Status: $($response.status)" -ForegroundColor White
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  ✅ ClawdbotConnector will automatically use this credential" -ForegroundColor Green
    Write-Host "  ✅ Set EDON_CREDENTIALS_STRICT=true to require database credentials (production)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "The connector will:" -ForegroundColor Cyan
    Write-Host "  1. Try to load credential 'clawdbot_gateway' from database" -ForegroundColor Gray
    Write-Host "  2. Fall back to CLAWDBOT_GATEWAY_URL/TOKEN env vars if not found (dev mode)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Note: Use EDON_API_TOKEN (from .env) or a tenant API key for X-EDON-TOKEN header" -ForegroundColor Yellow
    Write-Host ""
    
} catch {
    Write-Host "❌ Error setting credentials:" -ForegroundColor Red
    if ($_.Exception.Response) {
        $statusCode = $_.Exception.Response.StatusCode.value__
        $errorBody = $_.ErrorDetails.Message
        Write-Host "  HTTP $statusCode" -ForegroundColor Red
        Write-Host "  $errorBody" -ForegroundColor Red
    } else {
        Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
    }
    Write-Host ""
    exit 1
}
