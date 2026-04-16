import os
import pandas as pd
import numpy as np
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

MIN_AVG_DAILY_VALUE_CR = 10  # liquidity gate: ₹10 crore average daily traded value


def load_data():
    with engine.connect() as conn:
        prices = pd.read_sql("SELECT * FROM price_history", conn)
        fundamentals = pd.read_sql("SELECT * FROM fundamentals", conn)
        sentiment_row = pd.read_sql("SELECT * FROM market_sentiment WHERE id = 1", conn)

    prices["date"] = pd.to_datetime(prices["date"])
    return prices, fundamentals, sentiment_row


def calculate_indicators(df):
    """For a single ticker's price df sorted by date ascending."""
    df = df.sort_values("date").copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # EMAs
    df["ema20"] = close.ewm(span=20).mean()
    df["ema50"] = close.ewm(span=50).mean()

    # RSI 14
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(com=13).mean()
    loss = (-delta.clip(upper=0)).ewm(com=13).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    # MACD histogram (12, 26, 9)
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9).mean()
    df["macd_hist"] = macd_line - signal_line

    # ATR 14
    prev_close = close.shift(1)
    tr = pd.DataFrame({
        "hl": high - low,
        "hc": (high - prev_close).abs(),
        "lc": (low - prev_close).abs()
    }).max(axis=1)
    df["atr14"] = tr.ewm(span=14).mean()

    # Volume 20-day average
    df["vol_avg20"] = volume.rolling(20).mean()

    # 52-week high
    df["high_52w"] = high.rolling(252).max()

    return df


def liquidity_check(df):
    """Returns True if stock passes ₹10cr avg daily traded value filter."""
    recent = df.tail(20).copy()
    recent["traded_value"] = recent["close"] * recent["volume"]
    avg_value_cr = recent["traded_value"].mean() / 1e7  # convert to crores
    return avg_value_cr >= MIN_AVG_DAILY_VALUE_CR


def score_technical(row):
    score = 0.0
    signal_type = "NEUTRAL"

    price = row["close"]
    ema20 = row["ema20"]
    ema50 = row["ema50"]
    rsi = row["rsi"]
    macd_hist = row["macd_hist"]
    volume = row["volume"]
    vol_avg20 = row["vol_avg20"]
    high_52w = row["high_52w"]
    atr14 = row["atr14"]

    # --- Trend: 2.5 pts ---
    if price > ema20 and ema20 > ema50:
        score += 2.5
        signal_type = "MOMENTUM"
    elif price > ema50:
        score += 1.5
    else:
        score += 0.0

    # --- Momentum (RSI + MACD): 3.0 pts ---
    if 52 <= rsi <= 68:
        score += 2.5
    elif 45 <= rsi < 52 or 68 < rsi <= 75:
        score += 1.5
    elif rsi > 75:
        score += 0.5
    else:
        score += 0.5

    if macd_hist > 0:
        score += min(0.5, 0.5)  # capped bonus

    # --- Volume confirmation: 2.5 pts ---
    if vol_avg20 > 0:
        vol_ratio = volume / vol_avg20
        if vol_ratio >= 1.5:
            score += 2.5
        elif vol_ratio >= 1.2:
            score += 1.5
        else:
            score += 0.5
        volume_ratio = round(float(vol_ratio), 2)
    else:
        volume_ratio = None

    # --- Breakout: 2.0 pts ---
    if high_52w and high_52w > 0:
        pct_from_52w = (price - high_52w) / high_52w
        if pct_from_52w >= -0.02:
            score += 2.0
            signal_type = "BREAKOUT"
        elif pct_from_52w >= -0.05:
            score += 1.0
    else:
        pct_from_52w = None

    # Price vs EMA20 overextension
    price_vs_ema20_pct = round(((price - ema20) / ema20) * 100, 2) if ema20 else None

    return round(min(score, 10.0), 2), volume_ratio, price_vs_ema20_pct, signal_type


def score_valuation(pe_ratio, sector_median_pe):
    if pe_ratio is None or sector_median_pe is None or sector_median_pe == 0:
        return 5.0
    ratio = pe_ratio / sector_median_pe
    if ratio <= 0.6:
        return 10.0
    elif ratio <= 0.8:
        return 8.0
    elif ratio <= 1.0:
        return 6.0
    elif ratio <= 1.2:
        return 4.0
    elif ratio <= 1.5:
        return 2.0
    else:
        return 1.0


def compute_sector_medians(fundamentals):
    # Import SECTORS from universe
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from data.universe import SECTORS

    fundamentals["sector"] = fundamentals["ticker"].map(SECTORS)
    medians = (
        fundamentals.dropna(subset=["pe_ratio"])
        .groupby("sector")["pe_ratio"]
        .median()
        .to_dict()
    )
    return fundamentals, medians, SECTORS


def run_trade_scorer():
    print("Loading data...")
    prices, fundamentals, sentiment_row = load_data()

    if sentiment_row.empty:
        print("ERROR: No sentiment data found. Run fetch_market_data.py first.")
        return

    sentiment_score = float(sentiment_row["sentiment_score"].iloc[0])
    print(f"Market sentiment score: {sentiment_score}")

    fundamentals, sector_medians, SECTORS = compute_sector_medians(fundamentals)
    fund_map = fundamentals.set_index("ticker").to_dict("index")

    tickers = prices["ticker"].unique()
    results = []

    for ticker in tickers:
        df = prices[prices["ticker"] == ticker].copy()

        if len(df) < 60:
            continue

        if not liquidity_check(df):
            continue

        df = calculate_indicators(df)
        latest = df.iloc[-1]

        tech_score, volume_ratio, price_vs_ema20_pct, signal_type = score_technical(latest)

        fund = fund_map.get(ticker, {})
        pe_ratio = fund.get("pe_ratio")
        sector = SECTORS.get(ticker)
        sector_median_pe = sector_medians.get(sector)
        val_score = score_valuation(pe_ratio, sector_median_pe)

        # Weighted final trade score
        final_score = round(
            (tech_score * 0.65) + (sentiment_score * 0.20) + (val_score * 0.15),
            2
        )

        # Verdict with gates
        if final_score >= 7.5 and tech_score >= 7.0 and sentiment_score >= 6.0:
            verdict = "STRONG_BUY"
        elif final_score >= 6.5 and tech_score >= 6.0 and sentiment_score >= 5.0:
            verdict = "BUY"
        elif final_score >= 5.5:
            verdict = "WATCHLIST"
        else:
            verdict = "AVOID"

        # Target % by signal type — decoupled from ATR so R/R is meaningful
        TARGET_PCT = {
            "BREAKOUT": 0.10,  # 10% - near 52W high, strong continuation expected
            "MOMENTUM": 0.08,  # 8%  - trend intact, moderate move expected
            "NEUTRAL":  0.06,  # 6%  - no clear signal, conservative
        }

        # Trade parameters
        entry = round(float(latest["close"]), 2)
        atr14 = round(float(latest["atr14"]), 2) if not pd.isna(latest["atr14"]) else None

        # Stop: ATR-based (adapts to stock's actual volatility)
        if atr14 and atr14 > 0:
            stop_loss = round(entry - (1.5 * atr14), 2)
        else:
            stop_loss = round(entry * 0.94, 2)

        # Target: fixed % by signal type (meaningful expectation, not ATR multiple)
        target_pct = TARGET_PCT.get(signal_type, 0.08)
        target = round(entry * (1 + target_pct), 2)

        rr = round((target - entry) / (entry - stop_loss), 2) if (entry - stop_loss) > 0 else None
        near_52w_high = bool(
            not pd.isna(latest["high_52w"]) and
            ((latest["close"] - latest["high_52w"]) / latest["high_52w"]) >= -0.05
        )

        
        results.append({
            "ticker": ticker,
            "trade_score": final_score,
            "technical_score": tech_score,
            "sentiment_score": sentiment_score,
            "valuation_score": val_score,
            "verdict": verdict,
            "entry_price": entry,
            "target_price": target,
            "stop_loss": stop_loss,
            "atr14": atr14,
            "risk_reward": rr,
            "rsi": round(float(latest["rsi"]), 2) if not pd.isna(latest["rsi"]) else None,
            "ema20": round(float(latest["ema20"]), 2) if not pd.isna(latest["ema20"]) else None,
            "macd_signal": round(float(latest["macd_hist"]), 4) if not pd.isna(latest["macd_hist"]) else None,
            "volume_ratio": volume_ratio,
            "near_52w_high": near_52w_high,
            "price_vs_ema20_pct": price_vs_ema20_pct,
            "signal_type": signal_type,
            "scored_at": datetime.now(timezone.utc)
        })

    print(f"Scored {len(results)} stocks after liquidity filter")

    # Write to DB
    if IS_POSTGRES:
        with engine.connect() as conn:
            for r in results:
                conn.execute(text("""
                    INSERT INTO trade_signals (
                        ticker, trade_score, technical_score, sentiment_score, valuation_score,
                        verdict, entry_price, target_price, stop_loss, atr14, risk_reward,
                        rsi, ema20, macd_signal, volume_ratio, near_52w_high,
                        price_vs_ema20_pct, signal_type, scored_at
                    ) VALUES (
                        :ticker, :trade_score, :technical_score, :sentiment_score, :valuation_score,
                        :verdict, :entry_price, :target_price, :stop_loss, :atr14, :risk_reward,
                        :rsi, :ema20, :macd_signal, :volume_ratio, :near_52w_high,
                        :price_vs_ema20_pct, :signal_type, :scored_at
                    )
                    ON CONFLICT (ticker) DO UPDATE SET
                        trade_score = EXCLUDED.trade_score,
                        technical_score = EXCLUDED.technical_score,
                        sentiment_score = EXCLUDED.sentiment_score,
                        valuation_score = EXCLUDED.valuation_score,
                        verdict = EXCLUDED.verdict,
                        entry_price = EXCLUDED.entry_price,
                        target_price = EXCLUDED.target_price,
                        stop_loss = EXCLUDED.stop_loss,
                        atr14 = EXCLUDED.atr14,
                        risk_reward = EXCLUDED.risk_reward,
                        rsi = EXCLUDED.rsi,
                        ema20 = EXCLUDED.ema20,
                        macd_signal = EXCLUDED.macd_signal,
                        volume_ratio = EXCLUDED.volume_ratio,
                        near_52w_high = EXCLUDED.near_52w_high,
                        price_vs_ema20_pct = EXCLUDED.price_vs_ema20_pct,
                        signal_type = EXCLUDED.signal_type,
                        scored_at = EXCLUDED.scored_at
                """), r)
            conn.commit()
    else:
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM trade_signals"))
            for r in results:
                conn.execute(text("""
                    INSERT INTO trade_signals (
                        ticker, trade_score, technical_score, sentiment_score, valuation_score,
                        verdict, entry_price, target_price, stop_loss, atr14, risk_reward,
                        rsi, ema20, macd_signal, volume_ratio, near_52w_high,
                        price_vs_ema20_pct, signal_type, scored_at
                    ) VALUES (
                        :ticker, :trade_score, :technical_score, :sentiment_score, :valuation_score,
                        :verdict, :entry_price, :target_price, :stop_loss, :atr14, :risk_reward,
                        :rsi, :ema20, :macd_signal, :volume_ratio, :near_52w_high,
                        :price_vs_ema20_pct, :signal_type, :scored_at
                    )
                """), r)
            conn.commit()

    print("Trade signals written to DB.")


if __name__ == "__main__":
    run_trade_scorer()