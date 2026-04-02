#!/bin/bash
# Production Mode Validation Script
# Validates all three security invariants end-to-end

set -e

echo "============================================================"
echo "EDON Gateway Production Mode Validation"
echo "============================================================"
echo ""

# Configuration
GATEWAY_URL="${EDON_GATEWAY_URL:-http://localhost:8000}"
AUTH_TOKEN="${EDON_API_TOKEN:-test-token}"

# Check if server is running
echo "Checking if gateway is running at ${GATEWAY_URL}..."
if ! curl -s -f "${GATEWAY_URL}/health" > /dev/null; then
    echo "❌ ERROR: Gateway not running at ${GATEWAY_URL}"
    echo "   Start the gateway first: python -m uvicorn edon_gateway.main:app"
    exit 1
fi
echo "✓ Gateway is running"
echo ""

# Set production mode environment variables
export EDON_CREDENTIALS_STRICT=true
export EDON_VALIDATE_STRICT=true
export EDON_AUTH_ENABLED=true
export EDON_API_TOKEN="${AUTH_TOKEN}"

echo "Production Mode Configuration:"
echo "  EDON_CREDENTIALS_STRICT=true"
echo "  EDON_VALIDATE_STRICT=true"
echo "  EDON_AUTH_ENABLED=true"
echo ""

# Note: The server needs to be restarted with these env vars
# For now, we'll run the tests and document the expected behavior
echo "⚠️  NOTE: Server must be restarted with production env vars for full validation"
echo ""

# Run Python tests
echo "Running production mode tests..."
python edon_gateway/test_production_mode.py

echo ""
echo "============================================================"
echo "Validation Complete"
echo "============================================================"
