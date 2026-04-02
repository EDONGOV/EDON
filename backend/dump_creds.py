import sqlite3, json
db_path = r"C:\Users\cjbig\Desktop\EDON\edon-cav-engine\edon_gateway\edon_gateway.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables:", tables)
# Try both possible table names
table = None
for candidate in ("credentials", "credential", "secrets"):
    if candidate in tables:
        table = candidate
        break
if table is None:
    print("No credentials-like table found. Tables were:", tables)
    raise SystemExit(1)
# If your schema is different, this will fail loudly (good)
rows = cur.execute(f"""
  SELECT rowid, credential_id, tool_name, tenant_id, credential_data
  FROM {table}
  WHERE tool_name='clawdbot'
  ORDER BY rowid DESC
""").fetchall()
def tail(s):
    if s is None:
        return None
    s = str(s)
    return "..." + s[-6:] if len(s) >= 6 else s
print("\nClawdbot credentials:")
for rowid, credential_id, tool_name, tenant_id, credential_data in rows:
    try:
        data = json.loads(credential_data) if credential_data else {}
    except Exception:
        data = {"_raw": credential_data}
    secret = data.get("secret") or data.get("token") or data.get("gateway_token") or data.get("password")
    base_url = (data.get("base_url") or data.get("gateway_url") or "").rstrip("/")
    auth_mode = data.get("auth_mode")
    print(f"- rowid={rowid} cred_id={credential_id} tenant_id={tenant_id} auth_mode={auth_mode} base_url={base_url} secret_tail={tail(secret)}")
conn.close()
