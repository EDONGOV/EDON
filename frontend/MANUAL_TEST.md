# Manual Testing Guide - Agent UI with EDON Gateway

## Quick Test Checklist

### Step 1: Start Services

**Terminal 1 - Start Gateway:**
```powershell
cd C:\Users\cjbig\Desktop\EDON\edon-cav-engine\edon_gateway
python -m edon_gateway.main
```
✅ Verify: http://localhost:8000/docs shows API docs

**Terminal 2 - Start Agent UI:**
```powershell
cd C:\Users\cjbig\Desktop\edon-agent-ui
npm run dev
```
✅ Verify: http://localhost:5174 loads the UI

### Step 2: Connect UI to Gateway

1. Open http://localhost:5174 in browser
2. Open browser console (F12)
3. Run these commands:
```javascript
localStorage.setItem('edon_mock_mode', 'false');
localStorage.setItem('edon_api_base', 'http://localhost:8000');
location.reload();
```

### Step 3: Verify Connection

**Check Dashboard:**
- [ ] Dashboard loads without errors
- [ ] Metrics cards show data (may be zeros if no activity)
- [ ] Decision stream table loads (may be empty)

**Check Network Tab:**
- [ ] Requests to `http://localhost:8000/health` succeed (200)
- [ ] Requests to `http://localhost:8000/stats` succeed (200)
- [ ] Requests to `http://localhost:8000/decisions/query` succeed (200)

### Step 4: Test Clawdbot Integration

**Option A: Use curl/Postman**

```powershell
# Test Clawdbot invoke endpoint
curl -X POST http://localhost:8000/clawdbot/invoke `
  -H "Content-Type: application/json" `
  -H "X-Agent-ID: test-agent-123" `
  -d '{"tool": "sessions_list", "action": "json", "args": {}}'
```

**Option B: Use Python script**

Create `test_clawdbot.py`:
```python
import requests

url = "http://localhost:8000/clawdbot/invoke"
headers = {
    "Content-Type": "application/json",
    "X-Agent-ID": "test-agent-123"
}
data = {
    "tool": "sessions_list",
    "action": "json",
    "args": {}
}

response = requests.post(url, json=data, headers=headers)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
```

Run:
```powershell
python test_clawdbot.py
```

### Step 5: Verify in UI

After making a Clawdbot request:

1. **Check Dashboard:**
   - [ ] Metrics update (allowed/blocked counts)
   - [ ] Decision appears in decision stream

2. **Check Decisions Page:**
   - [ ] New decision appears
   - [ ] Verdict is correct (allowed/blocked/confirm)
   - [ ] Agent ID matches

3. **Check Audit Page:**
   - [ ] Audit entry created
   - [ ] All details visible
   - [ ] Timestamp correct

## Expected Behavior

### ✅ Success Indicators

- UI connects to gateway without errors
- Metrics load (even if zeros)
- Decisions appear after Clawdbot requests
- Audit logs show all activity
- No CORS errors in console
- No 404 errors for endpoints

### ⚠️ Common Issues

**Issue: UI shows mock data**
- **Fix:** Disable mock mode (see Step 2)

**Issue: CORS errors**
- **Fix:** Check gateway CORS config: `EDON_CORS_ORIGINS=http://localhost:5174`

**Issue: 401/403 errors**
- **Fix:** Either disable auth (`EDON_AUTH_ENABLED=false`) or set token

**Issue: Gateway not responding**
- **Fix:** Check gateway is running on port 8000
- **Fix:** Check firewall/antivirus isn't blocking

**Issue: Empty data**
- **Normal:** If no Clawdbot requests made yet
- **Test:** Make a Clawdbot request to generate data

## Testing with Real Clawdbot

If you have a real Clawdbot instance:

1. **Configure Clawdbot to use EDON Gateway:**
   - Change endpoint from `clawdbot-gateway:18789/tools/invoke`
   - To: `http://localhost:8000/clawdbot/invoke`
   - Add header: `X-EDON-TOKEN: your-token` (if auth enabled)

2. **Make Clawdbot requests:**
   - Let Clawdbot make normal tool calls
   - All calls go through EDON Gateway

3. **Monitor in UI:**
   - Watch decisions appear in real-time
   - Check metrics update
   - Review audit logs

## Test Results Template

```
Date: [Date]
Gateway Running: ✅ / ❌
UI Running: ✅ / ❌
Connection: ✅ / ❌
Health Check: ✅ / ❌
Metrics Load: ✅ / ❌
Decisions Load: ✅ / ❌
Clawdbot Test: ✅ / ❌
Issues Found: [List any issues]
```
