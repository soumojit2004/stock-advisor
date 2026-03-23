from __future__ import annotations

import logging
from pathlib import Path

import yfinance as yf
from dotenv import load_dotenv
from sqlalchemy import Date, Float, String, create_engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from backend.data.universe import TICKERS


class Base(DeclarativeBase):
    pass


class PriceHistory(Base):
    __tablename__ = "price_history"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    date: Mapped[Date] = mapped_column(Date, primary_key=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)


def _resolve_db_path() -> Path:
    load_dotenv()
    from os import getenv

    db_path = getenv("DB_PATH", "backend/db/stocks.db")
    return Path(db_path)


def _setup_logging() -> tuple[Path, logging.Logger]:
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    failed_path = logs_dir / "failed_tickers.txt"

    logger = logging.getLogger("price_fetch")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(logging.StreamHandler())
    return failed_path, logger


def _to_records(df, ticker: str) -> list[dict]:
    df = df.reset_index()
    df.columns = [str(c).lower() for c in df.columns]

    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(set(df.columns)):
        raise ValueError(f"Missing expected columns for {ticker}: {required - set(df.columns)}")

    records = []
    for row in df.itertuples(index=False):
        records.append(
            {
                "ticker": ticker,
                "date": row.date.date(),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": float(row.volume),
            }
        )
    return records


def main() -> None:
    failed_path, logger = _setup_logging()
    failed_path.write_text("", encoding="utf-8")

    from os import getenv
    database_url = getenv("DATABASE_URL")
    if database_url:
        if database_url.startswith("postgresql://"):
            database_url = "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
        engine = create_engine(database_url)
    else:
        db_path = _resolve_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        total = len(TICKERS)
        for idx, ticker in enumerate(TICKERS, start=1):
            try:
                ticker_obj = yf.Ticker(ticker)
                data = ticker_obj.history(period="2y", interval="1d", auto_adjust=True)

                if data.empty:
                    raise ValueError("Empty response")

                records = _to_records(data, ticker)
                insert_fn = pg_insert if database_url else sqlite_insert
                stmt = insert_fn(PriceHistory).values(records)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["ticker", "date"],
                    set_={
                        "open": stmt.excluded.open,
                        "high": stmt.excluded.high,
                        "low": stmt.excluded.low,
                        "close": stmt.excluded.close,
                        "volume": stmt.excluded.volume,
                    },
                )
                session.execute(stmt)
                session.commit()
            except Exception as exc:  # noqa: BLE001
                with failed_path.open("a", encoding="utf-8") as fh:
                    fh.write(f"{ticker}\n")
                logger.warning("Failed %s: %s", ticker, exc)
                session.rollback()

            if idx % 25 == 0 or idx == total:
                print(f"Processed {idx}/{total} tickers")

    print(f"Done. Failed tickers are logged at {failed_path}")


if __name__ == "__main__":
    main()
