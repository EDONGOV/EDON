# Setup Clawdbot credentials in EDON Gateway database
# Run this before running integration tests in production mode

param(
    [string]$EDON_URL = "http://127.0.0.1:8000",
    [string]$EDON_TOKEN = "your-secret-token",
    [string]$CLAWDBOT_URL = "http://127.0.0.1:18789",
    [string]$CLAWDBOT_TOKEN = ""
)

Write-Host "Setting up Clawdbot credentials in EDON Gateway..." -ForegroundColor Cyan
Write-Host ""

# Check if token is set
if (-not $EDON_TOKEN -or $EDON_TOKEN -eq "your-secret-token") {
    Write-Host "Warning: Using default token 'your-secret-token'" -ForegroundColor Yellow
    Write-Host "  Set -EDON_TOKEN parameter if using a different token"
    Write-Host ""
}

# Check if Clawdbot token is set
if (-not $CLAWDBOT_TOKEN) {
    Write-Host "Warning: CLAWDBOT_TOKEN not set" -ForegroundColor Yellow
    Write-Host "  Set -CLAWDBOT_TOKEN parameter or tests may fail"
    Write-Host ""
}

try {
    $headers = @{
        "X-EDON-TOKEN" = $EDON_TOKEN
        "Content-Type" = "application/json"
    }
    
    $body = @{
        credential_id = "clawdbot-gateway-001"
        tool_name = "clawdbot"
        credential_type = "gateway"
        credential_data = @{
            gateway_url = $CLAWDBOT_URL
            gateway_token = if ($CLAWDBOT_TOKEN) { $CLAWDBOT_TOKEN } else { "test-token-placeholder" }
        }
    } | ConvertTo-Json -Depth 10
    
    $response = Invoke-RestMethod -Uri "$EDON_URL/credentials/set" `
        -Method Post `
        -Headers $headers `
        -Body $body `
        -ErrorAction Stop
    
    Write-Host "Credentials set successfully!" -ForegroundColor Green
    Write-Host "  Credential ID: $($response.credential_id)"
    Write-Host "  Tool: $($response.tool_name)"
    Write-Host "  Status: $($response.status)"
    Write-Host ""
    Write-Host "You can now run integration tests:" -ForegroundColor Cyan
    Write-Host "  python edon_gateway/test_clawdbot_integration.py"
    
} catch {
    if ($_.Exception.Response) {
        $statusCode = $_.Exception.Response.StatusCode.value__
        Write-Host "Failed to set credentials: HTTP $statusCode" -ForegroundColor Red
        
        try {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $responseBody = $reader.ReadToEnd()
            Write-Host "  Response: $responseBody"
        } catch {
            Write-Host "  Could not read response body"
        }
    } else {
        Write-Host "Failed to set credentials: $($_.Exception.Message)" -ForegroundColor Red
    }
    
    exit 1
}
