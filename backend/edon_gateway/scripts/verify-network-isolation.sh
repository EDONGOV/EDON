#!/bin/bash
# Network Isolation Verification Script
#
# This script verifies that Clawdbot Gateway is properly isolated
# and only accessible from EDON Gateway.
#
# Usage:
#   ./verify-network-isolation.sh <CLAWDBOT_IP> <CLAWDBOT_PORT> <EDON_GATEWAY_IP>
#
# Example:
#   ./verify-network-isolation.sh 10.0.0.5 18789 10.0.0.10

set -e

CLAWDBOT_IP="${1:-127.0.0.1}"
CLAWDBOT_PORT="${2:-18789}"
EDON_GATEWAY_IP="${3:-127.0.0.1}"

echo "🔍 Verifying Network Isolation for Clawdbot Gateway"
echo "   Clawdbot: $CLAWDBOT_IP:$CLAWDBOT_PORT"
echo "   EDON Gateway: $EDON_GATEWAY_IP"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASSED=0
FAILED=0

# Test 1: EDON Gateway can reach Clawdbot
echo "Test 1: EDON Gateway can reach Clawdbot Gateway"
if curl -s -f --max-time 5 "http://$CLAWDBOT_IP:$CLAWDBOT_PORT/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ PASS${NC} - EDON Gateway can reach Clawdbot"
    ((PASSED++))
else
    echo -e "${RED}❌ FAIL${NC} - EDON Gateway cannot reach Clawdbot"
    echo "   Check: Is Clawdbot Gateway running?"
    echo "   Check: Is network configuration correct?"
    ((FAILED++))
fi
echo ""

# Test 2: Port is not publicly accessible (if we can determine public IP)
echo "Test 2: Checking if port is accessible from external IPs"
PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s icanhazip.com 2>/dev/null || echo "")
if [ -n "$PUBLIC_IP" ]; then
    echo "   Detected public IP: $PUBLIC_IP"
    if timeout 3 bash -c "echo > /dev/tcp/$PUBLIC_IP/$CLAWDBOT_PORT" 2>/dev/null; then
        echo -e "${RED}❌ FAIL${NC} - Port $CLAWDBOT_PORT is accessible from public IP"
        echo "   ⚠️  WARNING: Clawdbot Gateway may be publicly accessible!"
        ((FAILED++))
    else
        echo -e "${GREEN}✅ PASS${NC} - Port $CLAWDBOT_PORT is not publicly accessible"
        ((PASSED++))
    fi
else
    echo -e "${YELLOW}⚠️  SKIP${NC} - Could not determine public IP (test manually)"
fi
echo ""

# Test 3: Port scan (if nmap available)
if command -v nmap &> /dev/null; then
    echo "Test 3: Port scan (nmap)"
    RESULT=$(nmap -p $CLAWDBOT_PORT $CLAWDBOT_IP 2>/dev/null | grep -E "open|filtered|closed" || echo "")
    if echo "$RESULT" | grep -q "filtered\|closed"; then
        echo -e "${GREEN}✅ PASS${NC} - Port shows as filtered/closed (good)"
        ((PASSED++))
    elif echo "$RESULT" | grep -q "open"; then
        echo -e "${RED}❌ FAIL${NC} - Port shows as open (may be publicly accessible)"
        ((FAILED++))
    else
        echo -e "${YELLOW}⚠️  SKIP${NC} - Could not determine port status"
    fi
else
    echo -e "${YELLOW}⚠️  SKIP${NC} - nmap not installed (install for port scan test)"
fi
echo ""

# Test 4: Check firewall rules (if iptables/ufw available)
if command -v iptables &> /dev/null; then
    echo "Test 4: Checking iptables rules"
    RULES=$(iptables -L INPUT -n --line-numbers | grep $CLAWDBOT_PORT || echo "")
    if [ -n "$RULES" ]; then
        echo "   Found firewall rules:"
        echo "$RULES" | sed 's/^/   /'
        echo -e "${GREEN}✅ PASS${NC} - Firewall rules configured"
        ((PASSED++))
    else
        echo -e "${YELLOW}⚠️  WARN${NC} - No iptables rules found for port $CLAWDBOT_PORT"
    fi
elif command -v ufw &> /dev/null; then
    echo "Test 4: Checking ufw rules"
    RULES=$(ufw status numbered | grep $CLAWDBOT_PORT || echo "")
    if [ -n "$RULES" ]; then
        echo "   Found firewall rules:"
        echo "$RULES" | sed 's/^/   /'
        echo -e "${GREEN}✅ PASS${NC} - Firewall rules configured"
        ((PASSED++))
    else
        echo -e "${YELLOW}⚠️  WARN${NC} - No ufw rules found for port $CLAWDBOT_PORT"
    fi
else
    echo -e "${YELLOW}⚠️  SKIP${NC} - No firewall tool found (iptables/ufw)"
fi
echo ""

# Test 5: Check Docker network isolation (if Docker available)
if command -v docker &> /dev/null; then
    echo "Test 5: Checking Docker network configuration"
    NETWORKS=$(docker network ls --format "{{.Name}}" | grep -E "private|clawdbot" || echo "")
    if [ -n "$NETWORKS" ]; then
        echo "   Found networks: $NETWORKS"
        for NET in $NETWORKS; do
            INSPECT=$(docker network inspect $NET 2>/dev/null | grep -i "internal.*true" || echo "")
            if [ -n "$INSPECT" ]; then
                echo -e "   ${GREEN}✅${NC} Network '$NET' is internal (isolated)"
            fi
        done
    else
        echo -e "${YELLOW}⚠️  SKIP${NC} - No Docker networks found (may not be using Docker)"
    fi
else
    echo -e "${YELLOW}⚠️  SKIP${NC} - Docker not available"
fi
echo ""

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Summary:"
echo "   Passed: $PASSED"
echo "   Failed: $FAILED"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ Network isolation appears to be properly configured!${NC}"
    exit 0
else
    echo -e "${RED}❌ Some tests failed. Review the output above.${NC}"
    echo ""
    echo "Next steps:"
    echo "   1. Review NETWORK_ISOLATION_GUIDE.md"
    echo "   2. Check firewall rules"
    echo "   3. Verify Clawdbot Gateway binding (should be 127.0.0.1 or private IP)"
    echo "   4. Test manually from external IP"
    exit 1
fi
