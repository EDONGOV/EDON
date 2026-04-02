#!/bin/bash
# Quick test script for Clawdbot integration

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Clawdbot Integration Quick Test"
echo "=========================================="
echo ""

# Check environment variables
if [ -z "$CLAWDBOT_GATEWAY_TOKEN" ]; then
    echo -e "${YELLOW}Warning: CLAWDBOT_GATEWAY_TOKEN not set${NC}"
    echo "Set it with: export CLAWDBOT_GATEWAY_TOKEN='your-token'"
    echo ""
fi

if [ -z "$EDON_GATEWAY_TOKEN" ]; then
    echo -e "${YELLOW}Warning: EDON_GATEWAY_TOKEN not set${NC}"
    echo "Set it with: export EDON_GATEWAY_TOKEN='your-token'"
    echo ""
fi

# Defaults
CLAWDBOT_URL="${CLAWDBOT_GATEWAY_URL:-http://127.0.0.1:18789}"
EDON_URL="${EDON_GATEWAY_URL:-http://127.0.0.1:8000}"

echo "Step 1: Testing Clawdbot Gateway..."
echo "-----------------------------------"
if [ -z "$CLAWDBOT_GATEWAY_TOKEN" ]; then
    echo -e "${RED}✗ Skipped (no token)${NC}"
else
    response=$(curl -sS -w "\n%{http_code}" \
        -H "Authorization: Bearer $CLAWDBOT_GATEWAY_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"tool":"sessions_list","action":"json","args":{}}' \
        "$CLAWDBOT_URL/tools/invoke" 2>&1)
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" = "200" ]; then
        echo -e "${GREEN}✓ Clawdbot Gateway accessible${NC}"
        echo "Response: $body" | head -c 200
        echo "..."
    elif [ "$http_code" = "404" ]; then
        echo -e "${YELLOW}⚠ Clawdbot Gateway accessible but tool not allowlisted (404)${NC}"
    else
        echo -e "${RED}✗ Clawdbot Gateway error: HTTP $http_code${NC}"
    fi
fi

echo ""
echo "Step 2: Testing EDON Gateway..."
echo "--------------------------------"
response=$(curl -sS -w "\n%{http_code}" \
    "$EDON_URL/health" 2>&1)

http_code=$(echo "$response" | tail -n1)
if [ "$http_code" = "200" ]; then
    echo -e "${GREEN}✓ EDON Gateway accessible${NC}"
else
    echo -e "${RED}✗ EDON Gateway not accessible: HTTP $http_code${NC}"
    exit 1
fi

echo ""
echo "Step 3: Setting intent..."
echo "-------------------------"
if [ -z "$EDON_GATEWAY_TOKEN" ]; then
    echo -e "${RED}✗ Skipped (no token)${NC}"
else
    intent_response=$(curl -sS -w "\n%{http_code}" \
        -X POST \
        -H "X-EDON-TOKEN: $EDON_GATEWAY_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{
            "objective": "List Clawdbot sessions",
            "scope": {
                "clawdbot": ["invoke"]
            },
            "constraints": {},
            "risk_level": "low",
            "approved_by_user": true
        }' \
        "$EDON_URL/intent/set" 2>&1)
    
    http_code=$(echo "$intent_response" | tail -n1)
    body=$(echo "$intent_response" | sed '$d')
    
    if [ "$http_code" = "200" ]; then
        intent_id=$(echo "$body" | grep -o '"intent_id":"[^"]*"' | cut -d'"' -f4)
        echo -e "${GREEN}✓ Intent set: $intent_id${NC}"
        export INTENT_ID="$intent_id"
    else
        echo -e "${RED}✗ Failed to set intent: HTTP $http_code${NC}"
        echo "$body"
        exit 1
    fi
fi

echo ""
echo "Step 4: Testing ALLOW case..."
echo "------------------------------"
if [ -z "$EDON_GATEWAY_TOKEN" ] || [ -z "$INTENT_ID" ]; then
    echo -e "${YELLOW}⚠ Skipped (missing token or intent)${NC}"
else
    execute_response=$(curl -sS -w "\n%{http_code}" \
        -X POST \
        -H "X-EDON-TOKEN: $EDON_GATEWAY_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"action\": {
                \"tool\": \"clawdbot\",
                \"op\": \"invoke\",
                \"params\": {
                    \"tool\": \"sessions_list\",
                    \"action\": \"json\",
                    \"args\": {}
                }
            },
            \"intent_id\": \"$INTENT_ID\",
            \"agent_id\": \"test-agent-001\"
        }" \
        "$EDON_URL/execute" 2>&1)
    
    http_code=$(echo "$execute_response" | tail -n1)
    body=$(echo "$execute_response" | sed '$d')
    
    if [ "$http_code" = "200" ]; then
        verdict=$(echo "$body" | grep -o '"verdict":"[^"]*"' | cut -d'"' -f4)
        if [ "$verdict" = "ALLOW" ]; then
            echo -e "${GREEN}✓ ALLOW test passed${NC}"
        else
            echo -e "${YELLOW}⚠ Verdict: $verdict${NC}"
            echo "$body" | head -c 300
            echo "..."
        fi
    else
        echo -e "${RED}✗ Execute failed: HTTP $http_code${NC}"
        echo "$body"
    fi
fi

echo ""
echo "Step 5: Testing BLOCK case (out of scope)..."
echo "---------------------------------------------"
if [ -z "$EDON_GATEWAY_TOKEN" ]; then
    echo -e "${YELLOW}⚠ Skipped (missing token)${NC}"
else
    # Set intent without clawdbot
    intent_response=$(curl -sS -w "\n%{http_code}" \
        -X POST \
        -H "X-EDON-TOKEN: $EDON_GATEWAY_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{
            "objective": "Email only",
            "scope": {
                "email": ["send"]
            },
            "constraints": {},
            "risk_level": "low",
            "approved_by_user": true
        }' \
        "$EDON_URL/intent/set" 2>&1)
    
    http_code=$(echo "$intent_response" | tail -n1)
    body=$(echo "$intent_response" | sed '$d')
    
    if [ "$http_code" = "200" ]; then
        intent_id=$(echo "$body" | grep -o '"intent_id":"[^"]*"' | cut -d'"' -f4)
        
        # Try to execute clawdbot (should be blocked)
        execute_response=$(curl -sS -w "\n%{http_code}" \
            -X POST \
            -H "X-EDON-TOKEN: $EDON_GATEWAY_TOKEN" \
            -H "Content-Type: application/json" \
            -d "{
                \"action\": {
                    \"tool\": \"clawdbot\",
                    \"op\": \"invoke\",
                    \"params\": {
                        \"tool\": \"sessions_list\",
                        \"action\": \"json\",
                        \"args\": {}
                    }
                },
                \"intent_id\": \"$intent_id\",
                \"agent_id\": \"test-agent-001\"
            }" \
            "$EDON_URL/execute" 2>&1)
        
        http_code=$(echo "$execute_response" | tail -n1)
        body=$(echo "$execute_response" | sed '$d')
        
        if [ "$http_code" = "200" ]; then
            verdict=$(echo "$body" | grep -o '"verdict":"[^"]*"' | cut -d'"' -f4)
            if [ "$verdict" = "BLOCK" ]; then
                echo -e "${GREEN}✓ BLOCK test passed (scope violation)${NC}"
            else
                echo -e "${YELLOW}⚠ Verdict: $verdict (expected BLOCK)${NC}"
            fi
        else
            echo -e "${RED}✗ Execute failed: HTTP $http_code${NC}"
        fi
    fi
fi

echo ""
echo "=========================================="
echo "Quick test complete!"
echo "=========================================="
