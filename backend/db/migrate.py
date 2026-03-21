"""Migrate all data from SQLite to PostgreSQL."""

from __future__ import annotations

from os import getenv
from pathlib import Path
from typing import Any, Sequence, Type

from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import DeclarativeBase, Session

from backend.analysis.quality_filter import ScreenedStock
from backend.analysis.scorer import StockScore
from backend.data.fetch_fundamentals import Fundamentals
from backend.data.fetch_prices import PriceHistory


def _sqlite_url() -> str:
    load_dotenv()
    db_path = getenv("DB_PATH", "backend/db/stocks.db")
    path = Path(db_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return f"sqlite:///{path.resolve().as_posix()}"


def _pg_url() -> str:
    load_dotenv()
    url = getenv("DATABASE_URL")
    if not url:
        msg = "DATABASE_URL is not set in the environment or .env"
        raise RuntimeError(msg)
    # Prefer psycopg3 driver (postgresql+psycopg) when a generic URL is used.
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def _pk_index_elements(model: type[DeclarativeBase]) -> list[str]:
    return [c.name for c in model.__table__.primary_key.columns]


def _row_to_dict(obj: Any) -> dict[str, Any]:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def _create_pg_tables(pg_engine: Any) -> None:
    """Create all target tables on PostgreSQL using the same ORM table definitions."""
    for model in (PriceHistory, Fundamentals, ScreenedStock, StockScore):
        model.__table__.create(pg_engine, checkfirst=True)


def _migrate_table(
    sqlite_engine: Any,
    pg_engine: Any,
    model: Type[DeclarativeBase],
    label: str,
    *,
    batch_size: int = 500,
) -> None:
    with Session(sqlite_engine) as session:
        rows: Sequence[Any] = session.scalars(select(model)).all()

    total = len(rows)
    pk_cols = _pk_index_elements(model)

    if total == 0:
        print(f"Migrating {label}... {total} rows")
        return

    with Session(pg_engine) as session:
        for start in range(0, total, batch_size):
            batch = rows[start : start + batch_size]
            payloads = [_row_to_dict(r) for r in batch]
            stmt = pg_insert(model).values(payloads)
            stmt = stmt.on_conflict_do_nothing(index_elements=pk_cols)
            session.execute(stmt)
        session.commit()

    print(f"Migrating {label}... {total} rows")


def main() -> None:
    sqlite_url = _sqlite_url()
    pg_url = _pg_url()

    sqlite_engine = create_engine(sqlite_url)
    pg_engine = create_engine(pg_url, future=True)

    _create_pg_tables(pg_engine)

    _migrate_table(sqlite_engine, pg_engine, PriceHistory, "price_history")
    _migrate_table(sqlite_engine, pg_engine, Fundamentals, "fundamentals")
    _migrate_table(sqlite_engine, pg_engine, ScreenedStock, "screened_stocks")
    _migrate_table(sqlite_engine, pg_engine, StockScore, "stock_scores")

    sqlite_engine.dispose()
    pg_engine.dispose()

    print("Migration complete.")


if __name__ == "__main__":
    main()
