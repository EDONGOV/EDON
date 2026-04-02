#!/bin/bash
# Firewall Setup Script for Clawdbot Gateway Network Isolation
#
# This script configures iptables/ufw to allow only EDON Gateway
# to access Clawdbot Gateway on port 18789.
#
# Usage:
#   sudo ./setup-firewall-isolation.sh <EDON_GATEWAY_IP>
#
# Example:
#   sudo ./setup-firewall-isolation.sh 10.0.0.10

set -e

EDON_GATEWAY_IP="${1:-127.0.0.1}"
CLAWDBOT_PORT=18789

echo "🔒 Setting up firewall isolation for Clawdbot Gateway"
echo "   EDON Gateway IP: $EDON_GATEWAY_IP"
echo "   Clawdbot Port: $CLAWDBOT_PORT"

# Detect firewall system
if command -v ufw &> /dev/null; then
    echo "📋 Using UFW (Uncomplicated Firewall)"
    
    # Allow EDON Gateway IP
    ufw allow from $EDON_GATEWAY_IP to any port $CLAWDBOT_PORT comment "EDON Gateway access to Clawdbot"
    
    # Allow localhost
    ufw allow from 127.0.0.1 to any port $CLAWDBOT_PORT comment "Localhost access to Clawdbot"
    
    # Deny all other (default deny)
    echo "✅ UFW rules added. Default deny policy applies."
    echo "⚠️  Run 'ufw status' to verify rules"
    
elif command -v iptables &> /dev/null; then
    echo "📋 Using iptables"
    
    # Flush existing rules for this port (optional - be careful!)
    # iptables -D INPUT -p tcp --dport $CLAWDBOT_PORT -j DROP 2>/dev/null || true
    
    # Allow EDON Gateway IP
    iptables -A INPUT -p tcp --dport $CLAWDBOT_PORT -s $EDON_GATEWAY_IP -j ACCEPT
    
    # Allow localhost
    iptables -A INPUT -p tcp --dport $CLAWDBOT_PORT -s 127.0.0.1 -j ACCEPT
    
    # Deny all other connections to Clawdbot port
    iptables -A INPUT -p tcp --dport $CLAWDBOT_PORT -j DROP
    
    echo "✅ iptables rules added"
    
    # Try to save rules
    if command -v iptables-save &> /dev/null; then
        if [ -d /etc/iptables ]; then
            iptables-save > /etc/iptables/rules.v4
            echo "✅ Rules saved to /etc/iptables/rules.v4"
        elif command -v netfilter-persistent &> /dev/null; then
            netfilter-persistent save
            echo "✅ Rules saved via netfilter-persistent"
        else
            echo "⚠️  Rules added but not persisted. Run 'iptables-save > /etc/iptables/rules.v4' manually"
        fi
    fi
    
else
    echo "❌ Error: Neither ufw nor iptables found"
    echo "   Please install one of them:"
    echo "   - Ubuntu/Debian: apt-get install ufw"
    echo "   - CentOS/RHEL: yum install iptables-services"
    exit 1
fi

echo ""
echo "✅ Firewall isolation configured!"
echo ""
echo "📋 Verification commands:"
echo "   # Test from EDON Gateway (should succeed)"
echo "   curl http://localhost:$CLAWDBOT_PORT/health"
echo ""
echo "   # Test from external IP (should fail)"
echo "   curl http://<this-server-ip>:$CLAWDBOT_PORT/health"
echo ""
echo "   # Check firewall rules"
if command -v ufw &> /dev/null; then
    echo "   ufw status numbered"
else
    echo "   iptables -L INPUT -n --line-numbers | grep $CLAWDBOT_PORT"
fi
