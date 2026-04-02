#!/bin/bash
# Test script for Agent UI - Gateway Integration
# This script tests the agent UI against a running EDON Gateway

echo "Testing EDON Agent UI - Gateway Integration"
echo ""

# Check if gateway is running
GATEWAY_URL="http://localhost:8000"
echo "Checking if gateway is running at $GATEWAY_URL..."

if curl -s -f "$GATEWAY_URL/healthz" > /dev/null; then
    echo "✓ Gateway is running"
else
    echo "✗ Gateway is not running at $GATEWAY_URL"
    echo "  Please start the gateway first:"
    echo "  cd edon-cav-engine/edon_gateway"
    echo "  python -m edon_gateway.main"
    exit 1
fi

echo ""
echo "Running integration tests..."
echo ""

# Set environment variables for tests
export VITE_EDON_GATEWAY_URL="$GATEWAY_URL"
export VITE_EDON_GATEWAY_TOKEN=""  # Add token if auth is enabled

# Run tests
npm test

echo ""
echo "Tests completed!"
