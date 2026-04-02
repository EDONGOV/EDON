"""One-off: create tenant 'cj' and an API key. Run from edon_gateway: python create_cj_key.py"""
import uuid
import hashlib
import secrets
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

def main():
    db_path = os.getenv("EDON_DATABASE_PATH", str(Path(__file__).resolve().parent / "edon_gateway.db"))
    db_path = str(Path(db_path).resolve())
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    tenant_id = "cj"
    now = datetime.now(timezone.utc).isoformat()

    # User: get or create
    cur.execute("SELECT id FROM users WHERE auth_provider = ? AND auth_subject = ?", ("clerk", "demo_cj"))
    row = cur.fetchone()
    if row:
        user_id = row["id"]
    else:
        user_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO users (id, email, auth_provider, auth_subject, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, "cj@edoncore.com", "clerk", "demo_cj", "user", now, now),
        )

    # Tenant: get or create
    cur.execute("SELECT id FROM tenants WHERE id = ?", (tenant_id,))
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO tenants (id, user_id, status, plan, created_at, updated_at) VALUES (?, ?, 'active', 'starter', ?, ?)",
            (tenant_id, user_id, now, now),
        )

    # API key
    raw_key = secrets.token_hex(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key_id = "key_" + uuid.uuid4().hex[:16]
    cur.execute(
        "INSERT INTO api_keys (id, tenant_id, key_hash, name, status, created_at) VALUES (?, ?, ?, ?, 'active', ?)",
        (api_key_id, tenant_id, key_hash, "cj", now),
    )
    conn.commit()
    conn.close()

    print("Created tenant and API key.")
    print("tenant_id:", tenant_id)
    print("api_key_id:", api_key_id)
    print("api_key (save this, shown once):", raw_key)

if __name__ == "__main__":
    main()
