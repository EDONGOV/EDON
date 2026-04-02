# Network Isolation Guide for Clawdbot Gateway

## Overview

This guide provides three options to network-isolate Clawdbot Gateway so that only EDON Gateway can reach it, preventing agents from bypassing EDON and calling Clawdbot directly.

**Goal**: Clawdbot Gateway should NOT be accessible from the public internet or agent networks. Only EDON Gateway should be able to connect to it.

---

## Option 1: Docker Network Isolation (Recommended for Local/Container Deployments)

### Architecture

```
┌─────────────────┐         ┌──────────────────┐
│  Agent/Client   │────────▶│  EDON Gateway    │
│  (Public Net)   │         │  (Public Net)    │
└─────────────────┘         └────────┬─────────┘
                                     │
                                     │ Private Network
                                     ▼
                            ┌──────────────────┐
                            │ Clawdbot Gateway │
                            │  (Private Net)   │
                            └──────────────────┘
```

### Implementation

#### Step 1: Update docker-compose.yml

```yaml
services:
  edon-gateway:
    image: edon-gateway:local
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"  # Public port
    environment:
      - EDON_NETWORK_GATING=true
      - EDON_AUTH_ENABLED=true
      # ... other env vars
    networks:
      - public-network    # Accessible from internet
      - private-network   # Can reach Clawdbot

  clawdbot-gateway:
    image: clawdbot/gateway:latest
    # NO ports exposed to host - internal only
    environment:
      - CLAWDBOT_GATEWAY_TOKEN=${CLAWDBOT_GATEWAY_TOKEN}
    networks:
      - private-network   # Only accessible from private network
    restart: unless-stopped

networks:
  public-network:
    driver: bridge
    # Default bridge - accessible from host/internet
  
  private-network:
    driver: bridge
    internal: true  # CRITICAL: No external access
    # Containers on this network cannot reach internet
    # Only containers on both networks can reach it
```

#### Step 2: Configure EDON Gateway to use internal hostname

In EDON Gateway's `.env` or environment:

```bash
# Use Docker service name as hostname (resolves within Docker network)
CLAWDBOT_BASE_URL=http://clawdbot-gateway:18789
```

Or if using IP:

```bash
# Get Clawdbot Gateway's IP in private network
docker inspect clawdbot-gateway | grep IPAddress
# Use that IP
CLAWDBOT_BASE_URL=http://172.18.0.5:18789
```

#### Step 3: Verify Isolation

**Test 1: EDON Gateway can reach Clawdbot**
```bash
# From EDON Gateway container
docker exec edon-gateway curl http://clawdbot-gateway:18789/health
# Should succeed
```

**Test 2: Public internet cannot reach Clawdbot**
```bash
# From host machine (simulating agent)
curl http://localhost:18789/health
# Should fail: Connection refused (no port exposed)

# Try from external IP
curl http://<your-server-ip>:18789/health
# Should fail: Connection refused
```

**Test 3: Agent container cannot reach Clawdbot**
```bash
# Create test agent container (not on private-network)
docker run --rm --network public-network curlimages/curl \
  curl http://clawdbot-gateway:18789/health
# Should fail: Name resolution fails or connection refused
```

#### Step 4: Enable Network Gating Flag

```bash
# In EDON Gateway environment
EDON_NETWORK_GATING=true
```

---

## Option 2: Firewall Rules (Recommended for Cloud/VPS Deployments)

### Architecture

```
┌─────────────────┐         ┌──────────────────┐
│  Agent/Client   │────────▶│  EDON Gateway    │
│  (Internet)     │         │  (Public IP)     │
└─────────────────┘         └────────┬─────────┘
                                     │
                                     │ Internal IP
                                     │ (Firewall allows)
                                     ▼
                            ┌──────────────────┐
                            │ Clawdbot Gateway │
                            │  (Private IP)    │
                            │  Firewall: DENY  │
                            └──────────────────┘
```

### Implementation

#### Step 1: Deploy Clawdbot Gateway on Private IP

**AWS EC2 Example:**
- Deploy Clawdbot Gateway on private subnet (no public IP)
- Or use private IP even if instance has public IP

**VPS Example:**
- Bind Clawdbot Gateway to `127.0.0.1` or private IP (e.g., `10.0.0.5`)
- Do NOT bind to `0.0.0.0` (all interfaces)

#### Step 2: Configure Firewall Rules

**Linux (iptables) Example:**

```bash
# Allow EDON Gateway (on same host or specific IP) to reach Clawdbot
# Replace 10.0.0.10 with EDON Gateway's IP

# Allow EDON Gateway IP
iptables -A INPUT -p tcp --dport 18789 -s 10.0.0.10 -j ACCEPT

# Allow localhost (if EDON Gateway on same host)
iptables -A INPUT -p tcp --dport 18789 -s 127.0.0.1 -j ACCEPT

# Deny all other connections to Clawdbot port
iptables -A INPUT -p tcp --dport 18789 -j DROP

# Save rules (Ubuntu/Debian)
iptables-save > /etc/iptables/rules.v4

# Or use iptables-persistent
apt-get install iptables-persistent
netfilter-persistent save
```

**Linux (ufw) Example:**

```bash
# Allow EDON Gateway IP
ufw allow from 10.0.0.10 to any port 18789

# Allow localhost
ufw allow from 127.0.0.1 to any port 18789

# Deny all other (default deny)
ufw default deny incoming
```

**Cloud Provider Firewall Rules:**

**AWS Security Groups:**
```
Inbound Rules for Clawdbot Gateway:
- Type: Custom TCP
- Port: 18789
- Source: Security Group of EDON Gateway (sg-xxxxx)
- Action: Allow

Default: Deny all other traffic
```

**GCP Firewall Rules:**
```bash
gcloud compute firewall-rules create allow-clawdbot-from-edon \
  --allow tcp:18789 \
  --source-ranges 10.0.0.10/32 \
  --target-tags clawdbot-gateway \
  --direction INGRESS
```

**Azure Network Security Groups:**
```
Inbound Rule:
- Priority: 100
- Source: IP Address (EDON Gateway IP) or Application Security Group
- Destination: Clawdbot Gateway IP
- Port: 18789
- Action: Allow

Default Rule (Priority 4096): Deny all
```

#### Step 3: Configure EDON Gateway

```bash
# Use private IP or hostname
CLAWDBOT_BASE_URL=http://10.0.0.5:18789
# Or if on same host
CLAWDBOT_BASE_URL=http://127.0.0.1:18789
```

#### Step 4: Verify Isolation

**Test 1: EDON Gateway can reach Clawdbot**
```bash
# From EDON Gateway host
curl http://10.0.0.5:18789/health
# Should succeed
```

**Test 2: External IP cannot reach Clawdbot**
```bash
# From external machine (simulating agent)
curl http://<clawdbot-public-ip>:18789/health
# Should fail: Connection timeout or refused
```

**Test 3: Port scan verification**
```bash
# From external machine
nmap -p 18789 <clawdbot-public-ip>
# Should show: filtered or closed (not open)
```

---

## Option 3: Reverse Proxy (Recommended for Complex Setups)

### Architecture

```
┌─────────────────┐         ┌──────────────────┐
│  Agent/Client   │────────▶│  EDON Gateway    │
│  (Internet)     │         │  (Public IP)     │
└─────────────────┘         └────────┬─────────┘
                                     │
                                     │ Internal
                                     ▼
                            ┌──────────────────┐
                            │  Reverse Proxy   │
                            │  (nginx/traefik)  │
                            │  IP Whitelist    │
                            └────────┬─────────┘
                                     │
                                     ▼
                            ┌──────────────────┐
                            │ Clawdbot Gateway │
                            │  (Private IP)    │
                            └──────────────────┘
```

### Implementation

#### Step 1: Set up Reverse Proxy (nginx example)

**nginx.conf:**

```nginx
# Upstream to Clawdbot Gateway
upstream clawdbot_backend {
    server 127.0.0.1:18789;  # Or private IP
    keepalive 32;
}

# Server block for Clawdbot Gateway
server {
    listen 18789;
    server_name _;

    # IP Whitelist: Only allow EDON Gateway
    # Replace with EDON Gateway's IP(s)
    allow 10.0.0.10;      # EDON Gateway IP
    allow 127.0.0.1;     # Localhost (if same host)
    deny all;            # Deny all others

    # Logging
    access_log /var/log/nginx/clawdbot_access.log;
    error_log /var/log/nginx/clawdbot_error.log;

    # Proxy settings
    location / {
        proxy_pass http://clawdbot_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 10s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

**Alternative: Use nginx auth module for token-based access**

```nginx
# Use HTTP Basic Auth or custom header
location / {
    # Check for EDON Gateway secret header
    if ($http_x_edon_secret != "your-secret-token") {
        return 403;
    }
    
    proxy_pass http://clawdbot_backend;
    # ... proxy settings
}
```

#### Step 2: Configure Clawdbot Gateway

Bind Clawdbot Gateway to localhost only:

```bash
# Clawdbot Gateway config
CLAWDBOT_BIND=127.0.0.1:18789
# Not 0.0.0.0:18789 (would expose publicly)
```

#### Step 3: Configure EDON Gateway

```bash
# Point to reverse proxy (which enforces IP whitelist)
CLAWDBOT_BASE_URL=http://10.0.0.5:18789
# Or if using custom header auth
CLAWDBOT_BASE_URL=http://10.0.0.5:18789
X-EDON-SECRET=your-secret-token
```

#### Step 4: Alternative Reverse Proxy Options

**Traefik Example:**

```yaml
# docker-compose.yml
services:
  traefik:
    image: traefik:v2.10
    command:
      - "--api.insecure=true"
      - "--providers.docker=true"
      - "--entrypoints.web.address=:18789"
    ports:
      - "18789:18789"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    networks:
      - private-network

  clawdbot-gateway:
    image: clawdbot/gateway:latest
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.clawdbot.rule=Host(`clawdbot.internal`)"
      - "traefik.http.routers.clawdbot.entrypoints=web"
      - "traefik.http.middlewares.clawdbot-ipwhitelist.ipwhitelist.sourcerange=10.0.0.10/32,127.0.0.1/32"
      - "traefik.http.routers.clawdbot.middlewares=clawdbot-ipwhitelist"
    networks:
      - private-network
```

**Caddy Example:**

```
clawdbot.internal:18789 {
    @allowed {
        remote_ip 10.0.0.10 127.0.0.1
    }
    
    reverse_proxy @allowed http://127.0.0.1:18789 {
        header_up X-Real-IP {remote_host}
    }
    
    respond @not_allowed 403
}
```

#### Step 5: Verify Isolation

**Test 1: EDON Gateway can reach Clawdbot via proxy**
```bash
curl http://10.0.0.5:18789/health
# Should succeed
```

**Test 2: External IP cannot reach Clawdbot**
```bash
# From external machine
curl http://<proxy-public-ip>:18789/health
# Should fail: 403 Forbidden (nginx) or connection refused
```

---

## Verification Checklist

After implementing any option, verify:

- [ ] EDON Gateway can connect to Clawdbot Gateway
- [ ] External IPs cannot connect to Clawdbot Gateway
- [ ] Port scan shows Clawdbot port as filtered/closed
- [ ] `EDON_NETWORK_GATING=true` is set
- [ ] EDON Gateway logs show successful Clawdbot connections
- [ ] No Clawdbot Gateway logs show external connection attempts

## Testing Commands

```bash
# 1. Test from EDON Gateway (should succeed)
curl -H "X-EDON-TOKEN: $EDON_API_TOKEN" \
  http://clawdbot-gateway:18789/tools/invoke \
  -d '{"tool": "sessions_list"}'

# 2. Test from external (should fail)
curl http://<clawdbot-ip>:18789/health
# Expected: Connection refused/timeout or 403

# 3. Port scan (should show filtered)
nmap -p 18789 <clawdbot-ip>

# 4. Check EDON Gateway can reach Clawdbot
docker exec edon-gateway curl http://clawdbot-gateway:18789/health
```

## Security Best Practices

1. **Defense in Depth**: Combine network isolation with token hardening
2. **Monitor**: Log all connection attempts to Clawdbot Gateway
3. **Rotate**: Regularly rotate Clawdbot Gateway tokens
4. **Audit**: Review firewall/proxy logs for unauthorized access attempts
5. **Test**: Regularly test that isolation is working

## Troubleshooting

**Issue: EDON Gateway cannot reach Clawdbot**
- Check network configuration (Docker networks, firewall rules)
- Verify Clawdbot Gateway is running and bound to correct interface
- Check DNS resolution (use IP if hostname fails)
- Review firewall logs

**Issue: External IPs can still reach Clawdbot**
- Verify firewall rules are applied and saved
- Check if Clawdbot Gateway is bound to 0.0.0.0 (should be 127.0.0.1 or private IP)
- Review reverse proxy configuration
- Test with `nmap` or `telnet` from external IP

**Issue: Docker network isolation not working**
- Verify `internal: true` is set on private network
- Check containers are on correct networks
- Use `docker network inspect` to verify network configuration

---

## Next Steps

After implementing network isolation:

1. Set `EDON_NETWORK_GATING=true` in EDON Gateway environment
2. Verify isolation with test commands above
3. Monitor logs for any bypass attempts
4. Document your specific setup for your team
