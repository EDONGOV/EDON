# Quick test script for Clawdbot integration (PowerShell)

$ErrorActionPreference = "Stop"

# Colors (PowerShell)
function Write-Green { Write-Host $args -ForegroundColor Green }
function Write-Red { Write-Host $args -ForegroundColor Red }
function Write-Yellow { Write-Host $args -ForegroundColor Yellow }

Write-Host "=========================================="
Write-Host "Clawdbot Integration Quick Test"
Write-Host "=========================================="
Write-Host ""

# Check environment variables
if (-not $env:CLAWDBOT_GATEWAY_TOKEN) {
    Write-Yellow "Warning: CLAWDBOT_GATEWAY_TOKEN not set"
    Write-Host "Set it with: `$env:CLAWDBOT_GATEWAY_TOKEN='your-token'"
    Write-Host ""
}

if (-not $env:EDON_GATEWAY_TOKEN) {
    Write-Yellow "Warning: EDON_GATEWAY_TOKEN not set"
    Write-Host "Set it with: `$env:EDON_GATEWAY_TOKEN='your-token'"
    Write-Host ""
}

# Defaults
$CLAWDBOT_URL = if ($env:CLAWDBOT_GATEWAY_URL) { $env:CLAWDBOT_GATEWAY_URL } else { "http://127.0.0.1:18789" }
$EDON_URL = if ($env:EDON_GATEWAY_URL) { $env:EDON_GATEWAY_URL } else { "http://127.0.0.1:8000" }

Write-Host "Step 1: Testing Clawdbot Gateway..."
Write-Host "-----------------------------------"
if (-not $env:CLAWDBOT_GATEWAY_TOKEN) {
    Write-Red "✗ Skipped (no token)"
} else {
    try {
        $headers = @{
            "Authorization" = "Bearer $env:CLAWDBOT_GATEWAY_TOKEN"
            "Content-Type" = "application/json"
        }
        $body = @{
            tool = "sessions_list"
            action = "json"
            args = @{}
        } | ConvertTo-Json
        
        $response = Invoke-RestMethod -Uri "$CLAWDBOT_URL/tools/invoke" `
            -Method Post `
            -Headers $headers `
            -Body $body `
            -ErrorAction Stop
        
        Write-Green "✓ Clawdbot Gateway accessible"
        Write-Host "Response: $($response | ConvertTo-Json -Compress)" | Select-Object -First 200
    } catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        if ($statusCode -eq 404) {
            Write-Yellow "⚠ Clawdbot Gateway accessible but tool not allowlisted (404)"
        } else {
            Write-Red "✗ Clawdbot Gateway error: HTTP $statusCode"
        }
    }
}

Write-Host ""
Write-Host "Step 2: Testing EDON Gateway..."
Write-Host "--------------------------------"
try {
    $response = Invoke-RestMethod -Uri "$EDON_URL/health" -Method Get -ErrorAction Stop
    Write-Green "✓ EDON Gateway accessible"
} catch {
    Write-Red "✗ EDON Gateway not accessible: $($_.Exception.Message)"
    exit 1
}

Write-Host ""
Write-Host "Step 3: Setting intent..."
Write-Host "-------------------------"
if (-not $env:EDON_GATEWAY_TOKEN) {
    Write-Red "✗ Skipped (no token)"
} else {
    try {
        $headers = @{
            "X-EDON-TOKEN" = $env:EDON_GATEWAY_TOKEN
            "Content-Type" = "application/json"
        }
        $body = @{
            objective = "List Clawdbot sessions"
            scope = @{
                clawdbot = @("invoke")
            }
            constraints = @{}
            risk_level = "low"
            approved_by_user = $true
        } | ConvertTo-Json -Depth 10
        
        $response = Invoke-RestMethod -Uri "$EDON_URL/intent/set" `
            -Method Post `
            -Headers $headers `
            -Body $body `
            -ErrorAction Stop
        
        $intentId = $response.intent_id
        Write-Green "✓ Intent set: $intentId"
        $script:INTENT_ID = $intentId
    } catch {
        Write-Red "✗ Failed to set intent: $($_.Exception.Message)"
        if ($_.Exception.Response) {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $responseBody = $reader.ReadToEnd()
            Write-Host $responseBody
        }
        exit 1
    }
}

Write-Host ""
Write-Host "Step 4: Testing ALLOW case..."
Write-Host "------------------------------"
if (-not $env:EDON_GATEWAY_TOKEN -or -not $script:INTENT_ID) {
    Write-Yellow "⚠ Skipped (missing token or intent)"
} else {
    try {
        $headers = @{
            "X-EDON-TOKEN" = $env:EDON_GATEWAY_TOKEN
            "Content-Type" = "application/json"
        }
        $body = @{
            action = @{
                tool = "clawdbot"
                op = "invoke"
                params = @{
                    tool = "sessions_list"
                    action = "json"
                    args = @{}
                }
            }
            intent_id = $script:INTENT_ID
            agent_id = "test-agent-001"
        } | ConvertTo-Json -Depth 10
        
        $response = Invoke-RestMethod -Uri "$EDON_URL/execute" `
            -Method Post `
            -Headers $headers `
            -Body $body `
            -ErrorAction Stop
        
        if ($response.verdict -eq "ALLOW") {
            Write-Green "✓ ALLOW test passed"
        } else {
            Write-Yellow "⚠ Verdict: $($response.verdict)"
            Write-Host ($response | ConvertTo-Json -Compress) | Select-Object -First 300
        }
    } catch {
        Write-Red "✗ Execute failed: $($_.Exception.Message)"
        if ($_.Exception.Response) {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $responseBody = $reader.ReadToEnd()
            Write-Host $responseBody
        }
    }
}

Write-Host ""
Write-Host "Step 5: Testing BLOCK case (out of scope)..."
Write-Host "---------------------------------------------"
if (-not $env:EDON_GATEWAY_TOKEN) {
    Write-Yellow "⚠ Skipped (missing token)"
} else {
    try {
        # Set intent without clawdbot
        $headers = @{
            "X-EDON-TOKEN" = $env:EDON_GATEWAY_TOKEN
            "Content-Type" = "application/json"
        }
        $body = @{
            objective = "Email only"
            scope = @{
                email = @("send")
            }
            constraints = @{}
            risk_level = "low"
            approved_by_user = $true
        } | ConvertTo-Json -Depth 10
        
        $response = Invoke-RestMethod -Uri "$EDON_URL/intent/set" `
            -Method Post `
            -Headers $headers `
            -Body $body `
            -ErrorAction Stop
        
        $intentId = $response.intent_id
        
        # Try to execute clawdbot (should be blocked)
        $body = @{
            action = @{
                tool = "clawdbot"
                op = "invoke"
                params = @{
                    tool = "sessions_list"
                    action = "json"
                    args = @{}
                }
            }
            intent_id = $intentId
            agent_id = "test-agent-001"
        } | ConvertTo-Json -Depth 10
        
        $response = Invoke-RestMethod -Uri "$EDON_URL/execute" `
            -Method Post `
            -Headers $headers `
            -Body $body `
            -ErrorAction Stop
        
        if ($response.verdict -eq "BLOCK") {
            Write-Green "✓ BLOCK test passed (scope violation)"
        } else {
            Write-Yellow "⚠ Verdict: $($response.verdict) (expected BLOCK)"
        }
    } catch {
        Write-Red "✗ Execute failed: $($_.Exception.Message)"
    }
}

Write-Host ""
Write-Host "=========================================="
Write-Host "Quick test complete!"
Write-Host "=========================================="
