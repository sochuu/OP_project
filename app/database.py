from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "app.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def _column_names(conn, table: str) -> list[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return [r[1] for r in rows]


def migrate_schema() -> None:
    """Добавить owner_hash в уже существующую SQLite без потери строк."""
    with engine.begin() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
        if "earnings" in tables:
            cols = _column_names(conn, "earnings")
            if "owner_hash" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE earnings ADD COLUMN owner_hash VARCHAR(64) NOT NULL DEFAULT ''"
                    )
                )
        if "settings" in tables:
            cols = _column_names(conn, "settings")
            if "owner_hash" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE settings ADD COLUMN owner_hash VARCHAR(64) NOT NULL DEFAULT ''"
                    )
                )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

