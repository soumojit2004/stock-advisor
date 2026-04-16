import os
import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
DB_PATH = os.getenv("DB_PATH", "backend/db/stocks.db")

if DATABASE_URL:
    engine = create_engine(DATABASE_URL.replace("postgresql://", "postgresql+psycopg://"))
else:
    engine = create_engine(f"sqlite:///{DB_PATH}")

IS_POSTGRES = DATABASE_URL is not None


def fetch_vix_and_nifty():
    print("Fetching VIX and Nifty 50 data...")

    vix_df = yf.download("^INDIAVIX", period="30d", interval="1d", progress=False)
    nifty_df = yf.download("^NSEI", period="60d", interval="1d", progress=False)

    if vix_df.empty or nifty_df.empty:
        print("ERROR: Could not fetch VIX or Nifty data")
        return None, None

    vix_close = float(vix_df["Close"].squeeze().dropna().iloc[-1])

    nifty_close_series = nifty_df["Close"].squeeze().dropna()
    nifty_close = float(nifty_close_series.iloc[-1])
    ema20 = float(nifty_close_series.ewm(span=20).mean().iloc[-1])
    ema50 = float(nifty_close_series.ewm(span=50).mean().iloc[-1])

    print(f"VIX: {vix_close:.2f} | Nifty: {nifty_close:.2f} | EMA20: {ema20:.2f} | EMA50: {ema50:.2f}")
    return vix_close, {"close": nifty_close, "ema20": ema20, "ema50": ema50}


def score_sentiment(vix, nifty_data):
    score = 0.0

    # VIX component — 4 points
    if vix < 15:
        score += 4.0
    elif vix < 20:
        score += 2.5
    else:
        score += 0.5

    # Nifty trend component — 3 points
    close, ema20, ema50 = nifty_data["close"], nifty_data["ema20"], nifty_data["ema50"]
    if close > ema20 and ema20 > ema50:
        score += 3.0
        nifty_trend = "BULLISH"
    elif close > ema50:
        score += 1.5
        nifty_trend = "NEUTRAL"
    else:
        score += 0.0
        nifty_trend = "BEARISH"

    # Advance/Decline — 3 points
    # We don't have live A/D data without a paid feed, so default to neutral
    # You can replace this with a scrape later
    advance_decline = 1.1
    score += 1.5

    # Market regime
    if score >= 7.5:
        regime = "TRENDING"
    elif score >= 5.0:
        regime = "CHOPPY"
    else:
        regime = "FALLING"

    return round(score, 2), nifty_trend, advance_decline, regime


def write_sentiment(vix, nifty_data, sentiment_score, nifty_trend, advance_decline, regime):
    now = datetime.now(timezone.utc)

    if IS_POSTGRES:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy import Table, MetaData

        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO market_sentiment
                    (id, india_vix, nifty_close, nifty_ema20, nifty_ema50,
                     nifty_trend, advance_decline, sentiment_score, market_regime, updated_at)
                VALUES
                    (1, :vix, :close, :ema20, :ema50,
                     :trend, :ad, :score, :regime, :updated_at)
                ON CONFLICT (id) DO UPDATE SET
                    india_vix = EXCLUDED.india_vix,
                    nifty_close = EXCLUDED.nifty_close,
                    nifty_ema20 = EXCLUDED.nifty_ema20,
                    nifty_ema50 = EXCLUDED.nifty_ema50,
                    nifty_trend = EXCLUDED.nifty_trend,
                    advance_decline = EXCLUDED.advance_decline,
                    sentiment_score = EXCLUDED.sentiment_score,
                    market_regime = EXCLUDED.market_regime,
                    updated_at = EXCLUDED.updated_at
            """), {
                "vix": vix,
                "close": nifty_data["close"],
                "ema20": nifty_data["ema20"],
                "ema50": nifty_data["ema50"],
                "trend": nifty_trend,
                "ad": advance_decline,
                "score": sentiment_score,
                "regime": regime,
                "updated_at": now
            })
            conn.commit()
    else:
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM market_sentiment WHERE id = 1"))
            conn.execute(text("""
                INSERT INTO market_sentiment
                    (id, india_vix, nifty_close, nifty_ema20, nifty_ema50,
                     nifty_trend, advance_decline, sentiment_score, market_regime, updated_at)
                VALUES (1, :vix, :close, :ema20, :ema50, :trend, :ad, :score, :regime, :updated_at)
            """), {
                "vix": vix, "close": nifty_data["close"],
                "ema20": nifty_data["ema20"], "ema50": nifty_data["ema50"],
                "trend": nifty_trend, "ad": advance_decline,
                "score": sentiment_score, "regime": regime, "updated_at": now
            })
            conn.commit()

    print(f"Sentiment written: {regime} | Score: {sentiment_score} | Nifty: {nifty_trend} | VIX: {vix}")


if __name__ == "__main__":
    vix, nifty_data = fetch_vix_and_nifty()
    if vix is not None:
        sentiment_score, nifty_trend, advance_decline, regime = score_sentiment(vix, nifty_data)
        write_sentiment(vix, nifty_data, sentiment_score, nifty_trend, advance_decline, regime)
        print("Done.")
    else:
        print("Aborted — no data fetched.")