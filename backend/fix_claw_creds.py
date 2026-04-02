import sqlite3, json
db_path = r"C:\Users\cjbig\Desktop\EDON\edon-cav-engine\edon_gateway\edon_gateway.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()
def show():
    rows = cur.execute("""
      SELECT rowid, credential_id, tool_name, tenant_id, credential_data
      FROM credentials
      WHERE tool_name='clawdbot'
      ORDER BY rowid DESC
    """).fetchall()
    print("\nCurrent clawdbot rows:")
    for rowid, cred_id, tool, tenant_id, cred_data in rows:
        try:
            data = json.loads(cred_data) if cred_data else {}
        except Exception:
            data = {"_raw": cred_data}
        secret = data.get("secret") or data.get("token") or data.get("gateway_token") or data.get("password")
        tail = ("..." + secret[-6:]) if isinstance(secret, str) and len(secret) >= 6 else secret
        print(f"- rowid={rowid} cred_id={cred_id} tenant_id={tenant_id} auth_mode={data.get('auth_mode')} base_url={data.get('base_url') or data.get('gateway_url')} secret_tail={tail}")
show()
# 1) Force tenant_dev row (rowid=5) to the correct "token" secret
fixed = {
    "base_url": "http://127.0.0.1:18789",
    "auth_mode": "token",
    "secret": "dev_password_123"
}
cur.execute(
    "UPDATE credentials SET credential_data=? WHERE rowid=?",
    (json.dumps(fixed), 5)
)
# 2) Delete duplicates that can confuse selection
cur.execute("DELETE FROM credentials WHERE rowid IN (6,7)")
conn.commit()
print("\nApplied: updated rowid=5; deleted rowid=6,7")
show()
conn.close()
