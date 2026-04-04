# Database Migrations — EDON Gateway

EDON Gateway uses [Alembic](https://alembic.sqlalchemy.org/) for schema versioning.
Migrations live in `backend/alembic/versions/`.

---

## Quick Commands

```bash
cd backend

# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Check current migration state
alembic current

# Show migration history
alembic history

# Create a new migration (autogenerate from code changes)
alembic revision --autogenerate -m "add_usage_events_table"

# Create an empty migration (for manual SQL)
alembic revision -m "backfill_customer_ids"
```

---

## Creating a New Migration

1. Make your schema change (e.g., add a table or column to `database.py`)
2. Generate the migration:
   ```bash
   cd backend
   alembic revision --autogenerate -m "brief_description_of_change"
   ```
3. Review the generated file in `alembic/versions/`. **Always review before applying** — autogenerate can miss some changes.
4. Apply it locally:
   ```bash
   alembic upgrade head
   ```
5. Commit both the migration file and the `database.py` change together.

---

## Applying Migrations in Production (Fly.io)

Migrations must run **before** the new app code starts. The recommended pattern is to run them as a release command:

**Option 1: Fly.io release command (recommended)**

In `backend/fly.toml`, add:
```toml
[deploy]
  release_command = "alembic upgrade head"
```

This runs the migration before traffic is shifted to the new deployment. If the migration fails, the deploy is aborted.

**Option 2: Manual (before deploy)**

```bash
fly ssh console -a edon-gateway
cd /app && alembic upgrade head
exit
fly deploy
```

---

## Dual SQLite / PostgreSQL Support

The Alembic `env.py` reads the database URL in this order:

1. `DATABASE_URL` env var → PostgreSQL (e.g., `postgresql://user:pass@host/db`)
2. `EDON_DB_URL` env var → SQLite (e.g., `sqlite:///./data/edon_gateway.db`)
3. `EDON_DATABASE_PATH` env var → bare SQLite path
4. Default: `sqlite:///edon_gateway.db`

**SQLite-specific:** Alembic uses `render_as_batch=True` for SQLite because
SQLite doesn't support `ALTER TABLE` directly. Always test migrations against
both backends if you support both.

---

## Rollback

```bash
# Roll back one migration
alembic downgrade -1

# Roll back to a specific revision ID
alembic downgrade 001

# Roll back everything (dangerous — use only in dev)
alembic downgrade base
```

---

## Migration Naming Convention

Use snake_case, be descriptive:

```
002_add_usage_events_table.py
003_add_swarm_broadcast_column.py
004_backfill_tenant_retention_days.py
```

---

## Troubleshooting

**"Can't locate revision"** — run `alembic history` to see all known revisions.

**"Table already exists"** — your migration uses `CREATE TABLE` without `IF NOT EXISTS`. Add it, or mark the migration as already applied: `alembic stamp <rev>`.

**SQLite ALTER TABLE error** — make sure `render_as_batch=True` is set in `env.py`. All SQLite ALTERs must go through batch operations.
