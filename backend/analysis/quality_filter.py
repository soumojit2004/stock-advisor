from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Boolean, DateTime, Float, String, create_engine, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class Fundamentals(Base):
    __tablename__ = "fundamentals"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    pe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    roe: Mapped[float | None] = mapped_column(Float, nullable=True)
    debt_to_equity: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_profit_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_growth_3yr: Mapped[float | None] = mapped_column(Float, nullable=True)
    promoter_holding: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    roce: Mapped[float | None] = mapped_column(Float, nullable=True)


class ScreenedStock(Base):
    __tablename__ = "screened_stocks"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    quality_pass: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fail_reasons: Mapped[str | None] = mapped_column(String, nullable=True)
    watchlist: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    screened_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


def _resolve_db_path() -> Path:
    load_dotenv()
    from os import getenv

    db_path = getenv("DB_PATH", "backend/db/stocks.db")
    return Path(db_path)


def _evaluate_quality(row: Fundamentals) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    if row.revenue_growth_3yr is None:
        reasons.append("missing revenue growth")
    elif row.revenue_growth_3yr <= 10:
        reasons.append("revenue growth <= 10")

    if row.roe is None:
        reasons.append("missing ROE")
    elif row.roe <= 12:
        reasons.append("ROE <= 12")

    if row.net_profit_margin is None:
        reasons.append("missing margin")
    elif row.net_profit_margin <= 5:
        reasons.append("margin <= 5")

    if row.promoter_holding is None:
        reasons.append("missing promoter data")
    elif row.promoter_holding <= 40:
        reasons.append("promoter holding <= 40")

    # Intentionally skip D/E when missing (e.g., financials)
    if row.debt_to_equity is not None and row.debt_to_equity >= 1.5:
        reasons.append("debt to equity >= 1.5")

    return len(reasons) == 0, reasons


def _is_watchlist(reasons: list[str]) -> bool:
    if len(reasons) != 1:
        return False
    return not reasons[0].startswith("missing ")


def main() -> None:
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

    fail_counter: Counter[str] = Counter()
    total = 0
    total_passed = 0
    total_watchlist = 0

    with Session(engine) as session:
        fundamentals_rows = session.execute(select(Fundamentals)).scalars().all()

        for row in fundamentals_rows:
            total += 1
            quality_pass, reasons = _evaluate_quality(row)
            watchlist = _is_watchlist(reasons)

            if quality_pass:
                total_passed += 1
            if watchlist:
                total_watchlist += 1

            if reasons:
                fail_counter.update(reasons)

            values = {
                "ticker": row.ticker,
                "quality_pass": quality_pass,
                "fail_reasons": ", ".join(reasons) if reasons else None,
                "watchlist": watchlist,
                "screened_at": datetime.utcnow(),
            }

            stmt = sqlite_insert(ScreenedStock).values(values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["ticker"],
                set_={
                    "quality_pass": stmt.excluded.quality_pass,
                    "fail_reasons": stmt.excluded.fail_reasons,
                    "watchlist": stmt.excluded.watchlist,
                    "screened_at": stmt.excluded.screened_at,
                },
            )
            session.execute(stmt)

        session.commit()

    total_failed = total - total_passed

    print(f"Total stocks screened: {total}")
    print(f"Total passed: {total_passed}")
    print(f"Total watchlist: {total_watchlist}")
    print(f"Total failed: {total_failed}")
    print("Most common fail reasons:")
    if fail_counter:
        for reason, count in fail_counter.most_common():
            print(f"- {reason}: {count}")
    else:
        print("- none")


if __name__ == "__main__":
    main()
