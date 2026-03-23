from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import Boolean, Date, DateTime, Float, String, create_engine, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from backend.data.universe import SECTORS


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


class PriceHistory(Base):
    __tablename__ = "price_history"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    date: Mapped[Date] = mapped_column(Date, primary_key=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)


class ScreenedStock(Base):
    __tablename__ = "screened_stocks"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    quality_pass: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fail_reasons: Mapped[str | None] = mapped_column(String, nullable=True)
    watchlist: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    screened_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class StockScore(Base):
    __tablename__ = "stock_scores"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    business_quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    valuation_score: Mapped[float] = mapped_column(Float, nullable=False)
    technical_score: Mapped[float] = mapped_column(Float, nullable=False)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    verdict: Mapped[str] = mapped_column(String, nullable=False)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_reward: Mapped[float | None] = mapped_column(Float, nullable=True)
    rsi: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_vs_50dma: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_vs_200dma: Mapped[float | None] = mapped_column(Float, nullable=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


def _resolve_db_path() -> Path:
    load_dotenv()
    from os import getenv

    db_path = getenv("DB_PATH", "backend/db/stocks.db")
    return Path(db_path)


def _score_roe(x: float | None) -> float:
    if x is None:
        return 0.5
    if x >= 25:
        return 2.0
    if x >= 18:
        return 1.5
    if x >= 12:
        return 1.0
    return 0.0


def _score_roce(x: float | None) -> float:
    if x is None:
        return 0.5
    if x >= 25:
        return 2.0
    if x >= 18:
        return 1.5
    if x >= 12:
        return 1.0
    return 0.0


def _score_revenue_growth(x: float | None) -> float:
    if x is None:
        return 0.5
    if x >= 25:
        return 2.0
    if x >= 18:
        return 1.5
    if x >= 10:
        return 1.0
    return 0.0


def _score_net_margin(x: float | None) -> float:
    if x is None:
        return 0.5
    if x >= 20:
        return 2.0
    if x >= 12:
        return 1.5
    if x >= 5:
        return 1.0
    return 0.0


def _score_promoter(x: float | None) -> float:
    if x is None:
        return 0.5
    if x >= 65:
        return 2.0
    if x >= 50:
        return 1.5
    if x >= 40:
        return 1.0
    return 0.0


def business_quality_score(f: Fundamentals) -> float:
    s = (
        _score_roe(f.roe)
        + _score_roce(f.roce)
        + _score_revenue_growth(f.revenue_growth_3yr)
        + _score_net_margin(f.net_profit_margin)
        + _score_promoter(f.promoter_holding)
    )
    return min(10.0, s)


def _sector_median_pe(all_fundamentals: list[Fundamentals]) -> dict[str, float | None]:
    by_sector: dict[str, list[float]] = defaultdict(list)
    for row in all_fundamentals:
        sector = SECTORS.get(row.ticker)
        if sector is None or row.pe_ratio is None or row.pe_ratio <= 0:
            continue
        by_sector[sector].append(row.pe_ratio)
    out: dict[str, float | None] = {}
    for sec, vals in by_sector.items():
        out[sec] = median(vals) if vals else None
    return out


def valuation_score(pe: float | None, sector_median: float | None) -> float:
    if pe is None:
        return 5.0
    if sector_median is None or sector_median <= 0:
        return 5.0
    r = pe / sector_median
    if r <= 0.6:
        return 10.0
    if r <= 0.8:
        return 8.0
    if r <= 1.0:
        return 6.0
    if r <= 1.2:
        return 4.0
    if r <= 1.5:
        return 2.0
    return 1.0


def _pct_vs_ma(close: float, sma: float | None) -> float | None:
    if sma is None or sma == 0 or pd.isna(sma):
        return None
    return (close / float(sma) - 1.0) * 100.0


def _score_trend_200(pct_vs_200: float | None) -> float:
    if pct_vs_200 is None:
        return 0.0
    if pct_vs_200 > 5:
        return 3.0
    if pct_vs_200 > 0:
        return 2.0
    if -2 <= pct_vs_200 <= 0:
        return 1.0
    return 0.0


def _score_momentum_50(pct_vs_50: float | None) -> float:
    if pct_vs_50 is None:
        return 0.0
    if pct_vs_50 > 3:
        return 3.0
    if pct_vs_50 > 0:
        return 2.0
    if -2 <= pct_vs_50 <= 0:
        return 1.0
    return 0.0


def _score_rsi(rsi_val: float | None) -> float:
    if rsi_val is None or pd.isna(rsi_val):
        return 2.0
    rsi_f = float(rsi_val)
    if 40 <= rsi_f <= 60:
        return 4.0
    if 30 <= rsi_f < 40:
        return 3.0
    if 60 < rsi_f <= 70:
        return 2.0
    if rsi_f < 30:
        return 1.5
    return 0.5


def _calc_sma(close: pd.Series, length: int) -> pd.Series:
    return close.rolling(window=length, min_periods=length).mean()


def _calc_rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=length - 1, min_periods=length).mean()
    avg_loss = loss.ewm(com=length - 1, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def technical_from_prices(
    df: pd.DataFrame,
) -> tuple[float, float | None, float | None, float | None, float | None, float | None]:
    if df.empty or len(df) < 2:
        return 0.0, None, None, None, None, None

    df = df.sort_values("date").reset_index(drop=True)
    close = df["close"].astype(float)

    rsi_series = _calc_rsi(close, 14)
    sma50 = _calc_sma(close, 50)
    sma200 = _calc_sma(close, 200)

    last_close = float(close.iloc[-1])

    last_rsi = None
    if not pd.isna(rsi_series.iloc[-1]):
        last_rsi = float(rsi_series.iloc[-1])

    last_s50 = None
    if not pd.isna(sma50.iloc[-1]):
        last_s50 = float(sma50.iloc[-1])

    last_s200 = None
    if not pd.isna(sma200.iloc[-1]):
        last_s200 = float(sma200.iloc[-1])

    pv50 = _pct_vs_ma(last_close, last_s50)
    pv200 = _pct_vs_ma(last_close, last_s200)

    t200 = _score_trend_200(pv200)
    m50 = _score_momentum_50(pv50)
    r = _score_rsi(last_rsi)
    tech = min(10.0, t200 + m50 + r)

    return tech, last_rsi, pv50, pv200, last_close, last_s50


def verdict_for(
    final_score: float,
    technical_score: float,
    watchlist: bool,
) -> str:
    if final_score >= 7.0 and technical_score >= 5.0:
        return "BUY"
    if final_score >= 5.5 or watchlist:
        return "WATCHLIST"
    return "AVOID"


def risk_reward_ratio(entry: float | None, stop: float | None) -> float | None:
    if entry is None or stop is None or entry <= 0:
        return None
    if stop >= entry:
        return None
    target = entry * 1.15
    num = target - entry
    den = entry - stop
    if den == 0:
        return None
    return round(num / den, 2)


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

    with Session(engine) as session:
        all_f = list(session.execute(select(Fundamentals)).scalars().all())
        sector_medians = _sector_median_pe(all_f)
        f_by_ticker = {r.ticker: r for r in all_f}

        passed = session.execute(
            select(ScreenedStock).where(ScreenedStock.quality_pass == True)  # noqa: E712
        ).scalars().all()

        tickers = [s.ticker for s in passed]
        watch_by_ticker = {s.ticker: s.watchlist for s in passed}

        total_scored = 0
        buy_c = watch_c = avoid_c = 0
        short_data_count = 0
        total_to_score = sum(1 for t in tickers if t in f_by_ticker)
        done = 0

        for ticker in tickers:
            f = f_by_ticker.get(ticker)
            if f is None:
                continue

            sector = SECTORS.get(ticker)
            sm = sector_medians.get(sector) if sector else None
            vscore = valuation_score(f.pe_ratio, sm)

            bscore = business_quality_score(f)

            rows = session.execute(
                select(PriceHistory)
                .where(PriceHistory.ticker == ticker)
                .order_by(PriceHistory.date.desc())
                .limit(200)
            ).scalars().all()

            if len(rows) < 200:
                short_data_count += 1

            if not rows:
                tech = 0.0
                rsi_v = pv50 = pv200 = None
                entry = None
                stop = None
            else:
                df = pd.DataFrame(
                    [
                        {
                            "date": r.date,
                            "close": r.close,
                        }
                        for r in reversed(rows)
                    ]
                )
                tech, rsi_v, pv50, pv200, entry, last_s50 = technical_from_prices(df)
                if last_s50 is not None and entry is not None:
                    stop_50 = last_s50 * 0.98
                    stop = stop_50 if stop_50 < entry else entry * 0.93
                elif entry is not None:
                    stop = entry * 0.93
                else:
                    stop = None

            final = 0.5 * bscore + 0.25 * vscore + 0.25 * tech
            wl = watch_by_ticker.get(ticker, False)
            verdict = verdict_for(final, tech, wl)

            if verdict == "BUY":
                buy_c += 1
            elif verdict == "WATCHLIST":
                watch_c += 1
            else:
                avoid_c += 1

            rr = risk_reward_ratio(entry, stop)

            values = {
                "ticker": ticker,
                "business_quality_score": round(bscore, 4),
                "valuation_score": round(vscore, 4),
                "technical_score": round(tech, 4),
                "final_score": round(final, 4),
                "verdict": verdict,
                "entry_price": entry,
                "stop_loss": stop,
                "risk_reward": rr,
                "rsi": rsi_v,
                "price_vs_50dma": pv50,
                "price_vs_200dma": pv200,
                "scored_at": datetime.utcnow(),
            }

            stmt = sqlite_insert(StockScore).values(values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["ticker"],
                set_={
                    "business_quality_score": stmt.excluded.business_quality_score,
                    "valuation_score": stmt.excluded.valuation_score,
                    "technical_score": stmt.excluded.technical_score,
                    "final_score": stmt.excluded.final_score,
                    "verdict": stmt.excluded.verdict,
                    "entry_price": stmt.excluded.entry_price,
                    "stop_loss": stmt.excluded.stop_loss,
                    "risk_reward": stmt.excluded.risk_reward,
                    "rsi": stmt.excluded.rsi,
                    "price_vs_50dma": stmt.excluded.price_vs_50dma,
                    "price_vs_200dma": stmt.excluded.price_vs_200dma,
                    "scored_at": stmt.excluded.scored_at,
                },
            )
            session.execute(stmt)
            session.commit()

            total_scored += 1
            done += 1
            if done % 10 == 0 or done == total_to_score:
                print(f"Processed {done}/{total_to_score} quality-pass tickers")

    print()
    print(f"Total scored: {total_scored}")
    print(f"BUY: {buy_c}")
    print(f"WATCHLIST: {watch_c}")
    print(f"AVOID: {avoid_c}")
    print(f"Stocks with fewer than 200 price rows: {short_data_count}")


if __name__ == "__main__":
    main()
