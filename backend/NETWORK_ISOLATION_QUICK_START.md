# Network Isolation Quick Start

## Choose Your Option

### Option 1: Docker Network Isolation ⭐ (Easiest for Containers)

**Best for**: Local development, Docker deployments, containerized environments

**Quick Setup**:
```bash
# Use the provided docker-compose file
docker-compose -f docker-compose.network-isolation.yml up -d

# Verify
docker exec edon-gateway curl http://clawdbot-gateway:18789/health
```

**Files**:
- `docker-compose.network-isolation.yml` - Ready-to-use Docker Compose config

---

### Option 2: Firewall Rules ⭐ (Best for Cloud/VPS)

**Best for**: AWS EC2, GCP, Azure VMs, VPS deployments

**Quick Setup**:
```bash
# Linux (iptables)
sudo iptables -A INPUT -p tcp --dport 18789 -s <EDON_GATEWAY_IP> -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 18789 -s 127.0.0.1 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 18789 -j DROP

# Or use the script
sudo ./scripts/setup-firewall-isolation.sh <EDON_GATEWAY_IP>
```

**Files**:
- `scripts/setup-firewall-isolation.sh` - Automated firewall setup

---

### Option 3: Reverse Proxy ⭐ (Best for Complex Setups)

**Best for**: Multiple services, existing nginx/traefik infrastructure

**Quick Setup**:
```bash
# Copy nginx config
sudo cp nginx/clawdbot-isolation.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/clawdbot-isolation /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

**Files**:
- `nginx/clawdbot-isolation.conf` - Nginx reverse proxy config

---

## After Setup

1. **Set Environment Variable**:
   ```bash
   EDON_NETWORK_GATING=true
   ```

2. **Verify Isolation**:
   ```bash
   ./scripts/verify-network-isolation.sh <CLAWDBOT_IP> 18789 <EDON_GATEWAY_IP>
   ```

3. **Test from EDON Gateway** (should succeed):
   ```bash
   curl http://clawdbot-gateway:18789/health
   ```

4. **Test from External** (should fail):
   ```bash
   curl http://<clawdbot-public-ip>:18789/health
   # Expected: Connection refused/timeout or 403
   ```

---

## Full Documentation

See `NETWORK_ISOLATION_GUIDE.md` for detailed instructions, troubleshooting, and cloud-specific configurations.
