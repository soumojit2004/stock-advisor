from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from sqlalchemy import DateTime, Float, String, create_engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from backend.data.universe import TICKERS

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
REQUEST_DELAY_SECONDS = 1.5


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


def _resolve_db_path() -> Path:
    load_dotenv()
    from os import getenv

    db_path = getenv("DB_PATH", "backend/db/stocks.db")
    return Path(db_path)


def _setup_logging() -> tuple[Path, logging.Logger]:
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    failed_path = logs_dir / "failed_fundamentals.txt"

    logger = logging.getLogger("fundamentals_fetch")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(logging.StreamHandler())
    return failed_path, logger


def _extract_float(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = text.replace(",", "").replace("%", "").strip()
    if not cleaned or cleaned in {"-", "--", "NA", "N/A"}:
        return None

    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    return float(match.group(0)) if match else None


def _extract_top_ratios(soup: BeautifulSoup) -> dict[str, float | None]:
    values: dict[str, float | None] = {
        "pe_ratio": None,
        "roe": None,
        "debt_to_equity": None,
        "current_ratio": None,
        "roce": None,
    }

    for li in soup.select("ul#top-ratios li"):
        name_el = li.select_one(".name")
        value_el = li.select_one(".value")
        if not name_el or not value_el:
            continue

        label = name_el.get_text(" ", strip=True).lower()
        val = _extract_float(value_el.get_text(" ", strip=True))

        if "stock p/e" in label:
            values["pe_ratio"] = val
        elif label.startswith("roe"):
            values["roe"] = val
        elif "debt" in label and "equity" in label:
            values["debt_to_equity"] = val
        elif "current ratio" in label:
            values["current_ratio"] = val
        elif "roce" in label:
            values["roce"] = val

    return values


def _extract_from_table(soup: BeautifulSoup, key_match: str) -> float | None:
    for row in soup.select("table.data-table tr, table.ranges-table tr"):
        cols = row.find_all(["td", "th"])
        if len(cols) < 2:
            continue
        left = cols[0].get_text(" ", strip=True).lower()
        right = cols[1].get_text(" ", strip=True)
        if key_match in left:
            return _extract_float(right)
    return None


def _extract_promoter_holding(soup: BeautifulSoup) -> float | None:
    for row in soup.select("section#shareholding table tr"):
        cols = row.find_all(["td", "th"])
        if len(cols) < 2:
            continue
        left = cols[0].get_text(" ", strip=True).lower()
        if "promoter" in left:
            return _extract_float(cols[-1].get_text(" ", strip=True))
    return None


def _extract_growth_metrics(soup: BeautifulSoup) -> dict[str, float | None]:
    """Extract compounded growth rates from the unstructured growth section."""
    result = {"revenue_growth_3yr": None, "net_profit_margin": None}

    for div in soup.find_all(["div", "section", "ul"]):
        text = div.get_text(" ", strip=True)
        if "Compounded Sales Growth" in text and "3 Years" in text and len(text) < 800:
            match = re.search(r"3\s*Years\s*:\s*(-?\d+(?:\.\d+)?)\s*%", text)
            if match:
                result["revenue_growth_3yr"] = float(match.group(1))
            break

    # Net profit margin: extract from quarterly/annual table
    # Find most recent Net Profit and Sales rows and compute margin
    tables = soup.select("table.data-table")
    for table in tables:
        rows = table.find_all("tr")
        sales_row = None
        profit_row = None
        for row in rows:
            cols = row.find_all(["td", "th"])
            if not cols:
                continue
            label = cols[0].get_text(" ", strip=True).lower()
            if label.startswith("sales"):
                sales_row = cols
            elif label.startswith("net profit"):
                profit_row = cols
        if sales_row and profit_row and len(sales_row) > 1 and len(profit_row) > 1:
            # Use last available column (most recent period)
            sales = _extract_float(sales_row[-1].get_text(" ", strip=True))
            profit = _extract_float(profit_row[-1].get_text(" ", strip=True))
            if sales and profit and sales != 0:
                result["net_profit_margin"] = round((profit / sales) * 100, 2)
            break

    return result


def _scrape_metrics(html: str) -> dict[str, float | None]:
    soup = BeautifulSoup(html, "html.parser")
    metrics = _extract_top_ratios(soup)
    growth = _extract_growth_metrics(soup)
    metrics["revenue_growth_3yr"] = growth["revenue_growth_3yr"]
    metrics["net_profit_margin"] = growth["net_profit_margin"]
    metrics["promoter_holding"] = _extract_promoter_holding(soup)
    return metrics


def _to_screener_symbol(ticker: str) -> str:
    return ticker.removesuffix(".NS")


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

    headers = {"User-Agent": USER_AGENT}

    with Session(engine) as session:
        total = len(TICKERS)
        for idx, ticker in enumerate(TICKERS, start=1):
            symbol = _to_screener_symbol(ticker)
            url = f"https://www.screener.in/company/{symbol}/consolidated/"

            try:
                response = requests.get(url, headers=headers, timeout=20)
                if response.status_code == 404:
                    raise ValueError("404 Not Found")
                response.raise_for_status()

                metrics = _scrape_metrics(response.text)
                values = {
                    "ticker": ticker,
                    "fetched_at": datetime.utcnow(),
                    "pe_ratio": metrics.get("pe_ratio"),
                    "roe": metrics.get("roe"),
                    "debt_to_equity": metrics.get("debt_to_equity"),
                    "net_profit_margin": metrics.get("net_profit_margin"),
                    "revenue_growth_3yr": metrics.get("revenue_growth_3yr"),
                    "promoter_holding": metrics.get("promoter_holding"),
                    "current_ratio": metrics.get("current_ratio"),
                    "roce": metrics.get("roce"),
                }

                insert_fn = pg_insert if database_url else sqlite_insert
                stmt = insert_fn(Fundamentals).values(values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["ticker"],
                    set_={
                        "fetched_at": stmt.excluded.fetched_at,
                        "pe_ratio": stmt.excluded.pe_ratio,
                        "roe": stmt.excluded.roe,
                        "debt_to_equity": stmt.excluded.debt_to_equity,
                        "net_profit_margin": stmt.excluded.net_profit_margin,
                        "revenue_growth_3yr": stmt.excluded.revenue_growth_3yr,
                        "promoter_holding": stmt.excluded.promoter_holding,
                        "current_ratio": stmt.excluded.current_ratio,
                        "roce": stmt.excluded.roce,
                    },
                )
                session.execute(stmt)
                session.commit()
            except Exception as exc:  # noqa: BLE001
                with failed_path.open("a", encoding="utf-8") as fh:
                    fh.write(f"{ticker}\n")
                logger.warning("Failed %s (%s): %s", ticker, url, exc)
                session.rollback()

            if idx % 25 == 0 or idx == total:
                print(f"Processed {idx}/{total} tickers")

            time.sleep(REQUEST_DELAY_SECONDS)

    print(f"Done. Failed fundamentals are logged at {failed_path}")


if __name__ == "__main__":
    main()
