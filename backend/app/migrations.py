"""
Lightweight auto-migration helper.

This project uses `Base.metadata.create_all()` for initial table creation
but that call never alters EXISTING tables when new columns are added to a
model later. This module inspects the live database schema at startup and
issues `ALTER TABLE ... ADD COLUMN` statements for any columns that are
missing, so existing databases (SQLite) pick up schema changes without
requiring the user to delete their database.

This is intentionally simple (no down-migrations, no Alembic) and is safe
to call on every startup - it's a no-op once columns exist.
"""
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# Table -> list of (column_name, ddl_type_and_default) to ensure exist.
# ddl_type_and_default must be valid SQLite DDL. Add an entry here whenever a
# column is added to a model after a release; booleans are INTEGER 0/1.
_REQUIRED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "households": [
        ("crawl_enabled", "INTEGER DEFAULT 1"),
        ("crawl_time", "VARCHAR(10) DEFAULT '06:00'"),
        ("crawl_every_hours", "INTEGER DEFAULT 24"),
        ("crawl_handled_at", "DATETIME NULL"),
        ("ai_categorize", "INTEGER DEFAULT 0"),
    ],
    "articles": [
        ("canonical_url", "VARCHAR(1000) NULL"),
    ],
    "users": [
        ("feed_preferences", "TEXT DEFAULT '{}'"),
    ],
}


def run_lightweight_migrations(engine: Engine) -> set[str]:
    """Adds any missing columns defined in _REQUIRED_COLUMNS. Safe to call repeatedly.
    Returns the columns added ("table.column"), so one-time data fixes can run."""
    added: set[str] = set()
    try:
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())

        with engine.begin() as conn:
            for table_name, columns in _REQUIRED_COLUMNS.items():
                if table_name not in existing_tables:
                    # Table doesn't exist yet (fresh DB) - create_all() will handle it.
                    continue
                existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
                for col_name, ddl in columns:
                    if col_name not in existing_columns:
                        try:
                            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {ddl}"))
                            added.add(f"{table_name}.{col_name}")
                            print(f"[migrations] Added missing column {table_name}.{col_name}")
                        except Exception as e:
                            print(f"[migrations] Warning: could not add column {table_name}.{col_name}: {e}")
    except Exception as e:
        print(f"[migrations] Warning: lightweight migration check failed: {e}")
    return added
