# Database Migrations Guide

Agent Space uses [Alembic](https://alembic.sqlalchemy.org/) with SQLAlchemy 2.x async engine for version-controlled schema migrations.

---

## 1. Architecture

- Configuration: [alembic.ini](file:///home/anuj/Downloads/AgentSpace/alembic.ini)
- Environment script: [migrations/env.py](file:///home/anuj/Downloads/AgentSpace/migrations/env.py)
- Template: [migrations/script.py.mako](file:///home/anuj/Downloads/AgentSpace/migrations/script.py.mako)
- Versions directory: [migrations/versions/](file:///home/anuj/Downloads/AgentSpace/migrations/versions/)

Migrations automatically discover models registered on `app.database.Base.metadata`. The database connection URL is loaded from `app.config.get_settings().database_url` or can be overridden via command-line `-x db_url=<url>`.

---

## 2. Common Commands

### Apply Pending Migrations

Upgrade database schema to the latest version:

```bash
make db-migrate
# Or directly via Alembic:
python3 -m alembic upgrade head
```

### Generate a New Migration (Autogenerate)

After adding or modifying SQLAlchemy models in `apps/backend/app/models/`:

```bash
make db-makemigrations m="add_tasks_table"
# Or directly via Alembic:
python3 -m alembic revision --autogenerate -m "add_tasks_table"
```

> **Important**: Always inspect the generated migration file in `migrations/versions/` to verify column types, nullability, and constraints before applying.

### Check Current Migration Version

```bash
make db-current
# Or directly:
python3 -m alembic current
```

### View Migration History

```bash
make db-history
# Or directly:
python3 -m alembic history --verbose
```

### Rollback / Downgrade

Revert the most recent migration:

```bash
make db-downgrade
# Or directly:
python3 -m alembic downgrade -1
```

Rollback to clean baseline:

```bash
python3 -m alembic downgrade base
```

---

## 3. Custom Database URL

To run migrations against a specific database without editing `.env`:

```bash
python3 -m alembic -x db_url=postgresql+asyncpg://user:pass@host:5432/dbname upgrade head
```
