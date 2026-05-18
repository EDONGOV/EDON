# EDON Gateway — Database Migrations

Managed by [Alembic](https://alembic.sqlalchemy.org/).

## Run migrations

```bash
cd backend
alembic upgrade head
```

## Create a new migration

```bash
cd backend
alembic revision --autogenerate -m "add foo column to bar table"
```

The generated file lands in `edon_gateway/migrations/versions/`. Review it before committing.

## Use PostgreSQL (production / HIPAA)

```bash
export EDON_DB_URL=postgresql://user:password@host:5432/edon
alembic upgrade head
```

## SQLite (development default)

When `EDON_DB_URL` is not set, Alembic (and the gateway) use SQLite automatically.
The database file path is controlled by `EDON_DATABASE_PATH` (default: `edon_gateway.db`).

## Version table

Alembic stores its migration state in the `alembic_version` table in the target database.
