"""FastAPI app exposing stock scores from PostgreSQL."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from os import getenv
from typing import Annotated, Literal, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from backend.analysis.quality_filter import ScreenedStock
from backend.analysis.scorer import StockScore
from backend.data.fetch_fundamentals import Fundamentals
from backend.data.universe import SECTORS


def _database_url() -> str:
    load_dotenv()
    url = getenv("DATABASE_URL")
    if not url:
        msg = "DATABASE_URL is not set in the environment or .env"
        raise RuntimeError(msg)
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


engine = create_engine(_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI(title="Stock Advisor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── INVEST MODE MODELS ───────────────────────────────────────────────────────

class ScoreItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    sector: str | None
    verdict: str
    final_score: float | None
    business_quality_score: float | None
    valuation_score: float | None
    technical_score: float | None
    entry_price: float | None
    target_price: float | None
    stop_loss: float | None
    risk_reward: float | None
    rsi: float | None
    price_vs_50dma: float | None
    price_vs_200dma: float | None
    pe_ratio: float | None
    roe: float | None
    roce: float | None
    revenue_growth_3yr: float | None
    net_profit_margin: float | None
    promoter_holding: float | None
    debt_to_equity: float | None
    watchlist: bool


class SummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_scored: int
    buy_count: int
    watchlist_count: int
    avoid_count: int
    last_scored_at: datetime | None


class HealthResponse(BaseModel):
    status: str


# ─── INVEST MODE HELPERS ──────────────────────────────────────────────────────

def _to_score_item(ss: StockScore, fund: Fundamentals, scr: ScreenedStock) -> ScoreItem:
    return ScoreItem(
        ticker=ss.ticker,
        sector=SECTORS.get(ss.ticker),
        verdict=ss.verdict,
        final_score=ss.final_score,
        business_quality_score=ss.business_quality_score,
        valuation_score=ss.valuation_score,
        technical_score=ss.technical_score,
        entry_price=ss.entry_price,
        target_price=round(ss.entry_price * 1.15, 2) if ss.entry_price else None,
        stop_loss=ss.stop_loss,
        risk_reward=ss.risk_reward,
        rsi=ss.rsi,
        price_vs_50dma=ss.price_vs_50dma,
        price_vs_200dma=ss.price_vs_200dma,
        pe_ratio=fund.pe_ratio,
        roe=fund.roe,
        roce=fund.roce,
        revenue_growth_3yr=fund.revenue_growth_3yr,
        net_profit_margin=fund.net_profit_margin,
        promoter_holding=fund.promoter_holding,
        debt_to_equity=fund.debt_to_equity,
        watchlist=scr.watchlist,
    )


def _scores_base_query():
    return (
        select(StockScore, Fundamentals, ScreenedStock)
        .join(Fundamentals, StockScore.ticker == Fundamentals.ticker)
        .join(ScreenedStock, StockScore.ticker == ScreenedStock.ticker)
    )


# ─── INVEST MODE ENDPOINTS ────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/summary", response_model=SummaryResponse)
def api_summary(db: Annotated[Session, Depends(get_db)]) -> SummaryResponse:
    total = db.scalar(select(func.count(StockScore.ticker))) or 0
    buy_count = db.scalar(
        select(func.count(StockScore.ticker)).where(StockScore.verdict == "BUY")
    ) or 0
    watchlist_count = db.scalar(
        select(func.count(StockScore.ticker)).where(StockScore.verdict == "WATCHLIST")
    ) or 0
    avoid_count = db.scalar(
        select(func.count(StockScore.ticker)).where(StockScore.verdict == "AVOID")
    ) or 0
    last_scored_at = db.scalar(select(func.max(StockScore.scored_at)))

    return SummaryResponse(
        total_scored=int(total),
        buy_count=int(buy_count),
        watchlist_count=int(watchlist_count),
        avoid_count=int(avoid_count),
        last_scored_at=last_scored_at,
    )


@app.get("/api/scores", response_model=list[ScoreItem])
def api_scores(
    db: Annotated[Session, Depends(get_db)],
    verdict: Annotated[
        Literal["BUY", "WATCHLIST", "AVOID"] | None,
        Query(description="Filter by verdict"),
    ] = None,
) -> list[ScoreItem]:
    stmt = _scores_base_query()
    if verdict is not None:
        stmt = stmt.where(StockScore.verdict == verdict)
    stmt = stmt.order_by(StockScore.ticker)
    rows = db.execute(stmt).all()
    return [_to_score_item(ss, f, s) for ss, f, s in rows]


@app.get("/api/scores/{ticker}", response_model=ScoreItem)
def api_score_detail(ticker: str, db: Annotated[Session, Depends(get_db)]) -> ScoreItem:
    stmt = _scores_base_query().where(StockScore.ticker == ticker)
    row = db.execute(stmt).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Ticker not found")
    ss, f, s = row
    return _to_score_item(ss, f, s)


# ─── TRADE MODE ENDPOINTS ─────────────────────────────────────────────────────

@app.get("/api/trade/sentiment")
def get_market_sentiment():
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM market_sentiment WHERE id = 1")).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No sentiment data yet. Run fetch_market_data.py first.")
    return dict(row._mapping)


@app.get("/api/trade/summary")
def get_trade_summary():
    with engine.connect() as conn:
        counts = conn.execute(text(
            "SELECT verdict, COUNT(*) as count FROM trade_signals GROUP BY verdict"
        )).fetchall()
        sentiment = conn.execute(text(
            "SELECT sentiment_score, market_regime, nifty_trend, india_vix FROM market_sentiment WHERE id = 1"
        )).fetchone()

    verdict_counts = {row[0]: row[1] for row in counts}
    result = {"verdicts": verdict_counts}
    if sentiment:
        result["market"] = dict(sentiment._mapping)
    return result


@app.get("/api/trade/scores")
def get_trade_scores(verdict: Optional[str] = None):
    with engine.connect() as conn:
        if verdict:
            rows = conn.execute(text(
                "SELECT * FROM trade_signals WHERE verdict = :v ORDER BY trade_score DESC"
            ), {"v": verdict.upper()}).fetchall()
        else:
            rows = conn.execute(text(
                "SELECT * FROM trade_signals ORDER BY trade_score DESC"
            )).fetchall()
    return [dict(r._mapping) for r in rows]


@app.get("/api/trade/scores/{ticker}")
def get_trade_score_by_ticker(ticker: str):
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT * FROM trade_signals WHERE ticker = :t"
        ), {"t": ticker}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"{ticker} not found in trade signals")
    return dict(row._mapping)


@app.get("/api/trade/checklist/{ticker}")
def get_trade_checklist(ticker: str, price: float = 0, capital: float = 500000):
    with engine.connect() as conn:
        signal = conn.execute(text(
            "SELECT * FROM trade_signals WHERE ticker = :t"
        ), {"t": ticker}).fetchone()
        sentiment = conn.execute(text(
            "SELECT * FROM market_sentiment WHERE id = 1"
        )).fetchone()
        fund = conn.execute(text(
            "SELECT * FROM fundamentals WHERE ticker = :t"
        ), {"t": ticker}).fetchone()

    if not signal:
        raise HTTPException(status_code=404, detail=f"{ticker} not found in trade signals")

    s = dict(signal._mapping)
    m = dict(sentiment._mapping) if sentiment else {}
    f = dict(fund._mapping) if fund else {}

    TARGET_PCT = {"BREAKOUT": 0.10, "MOMENTUM": 0.08, "NEUTRAL": 0.06}

    entry = price if price > 0 else (s.get("entry_price") or 0)
    atr = s.get("atr14") or 0
    signal_type_val = s.get("signal_type") or "NEUTRAL"

    stop = round(entry - (1.5 * atr), 2) if atr and entry else round(entry * 0.94, 2)
    target_pct = TARGET_PCT.get(signal_type_val, 0.08)
    target = round(entry * (1 + target_pct), 2)

    stop_pct = round(((entry - stop) / entry) * 100, 2) if entry else 0
    rr = round((target - entry) / (entry - stop), 2) if entry and (entry - stop) > 0 else 0
    risk_per_trade = capital * 0.01
    qty = int(risk_per_trade / (entry - stop)) if (entry - stop) > 0 else 0
    capital_deployed = qty * entry
    capital_pct = round((capital_deployed / capital) * 100, 2) if capital else 0

    checks = []

    # --- Category A: Market ---
    vix = m.get("india_vix") or 20
    checks.append({
        "category": "market",
        "name": "India VIX",
        "value": round(vix, 2),
        "status": "GREEN" if vix < 15 else ("YELLOW" if vix < 20 else "RED"),
        "message": f"VIX {vix:.1f} — {'Calm' if vix < 15 else 'Elevated — trade smaller' if vix < 20 else 'High volatility — avoid new entries'}",
    })

    nifty_trend = m.get("nifty_trend") or "NEUTRAL"
    checks.append({
        "category": "market",
        "name": "Nifty 50 Trend",
        "value": nifty_trend,
        "status": "GREEN" if nifty_trend == "BULLISH" else ("YELLOW" if nifty_trend == "NEUTRAL" else "RED"),
        "message": f"Nifty is {nifty_trend.lower()}",
    })

    # --- Category B: Technicals ---
    rsi = s.get("rsi") or 50
    checks.append({
        "category": "technical",
        "name": "RSI Zone",
        "value": round(rsi, 1),
        "status": "GREEN" if 52 <= rsi <= 68 else ("YELLOW" if 45 <= rsi <= 75 else "RED"),
        "message": (
            f"RSI {rsi:.1f} — Good momentum zone" if 52 <= rsi <= 68
            else f"RSI {rsi:.1f} — Overbought, wait for pullback" if rsi > 75
            else f"RSI {rsi:.1f} — Weak momentum" if rsi < 45
            else f"RSI {rsi:.1f} — Acceptable"
        ),
    })

    vol_ratio = s.get("volume_ratio") or 0
    checks.append({
        "category": "technical",
        "name": "Volume Confirmation",
        "value": round(vol_ratio, 2),
        "status": "GREEN" if vol_ratio >= 1.3 else ("YELLOW" if vol_ratio >= 1.0 else "RED"),
        "message": (
            f"Volume {vol_ratio:.2f}x avg — Strong accumulation" if vol_ratio >= 1.3
            else f"Volume {vol_ratio:.2f}x avg — Average" if vol_ratio >= 1.0
            else f"Volume {vol_ratio:.2f}x avg — Below average, weak conviction"
        ),
    })

    pct_vs_ema20 = s.get("price_vs_ema20_pct") or 0
    checks.append({
        "category": "technical",
        "name": "Overextension from EMA20",
        "value": round(pct_vs_ema20, 2),
        "status": "GREEN" if pct_vs_ema20 <= 8 else ("YELLOW" if pct_vs_ema20 <= 12 else "RED"),
        "message": (
            f"{pct_vs_ema20:.1f}% above EMA20 — Fine" if pct_vs_ema20 <= 8
            else f"{pct_vs_ema20:.1f}% above EMA20 — Stretched" if pct_vs_ema20 <= 12
            else f"{pct_vs_ema20:.1f}% above EMA20 — Overextended, chasing risk"
        ),
    })

    # --- Category C: Risk ---
    checks.append({
        "category": "risk",
        "name": "Risk/Reward",
        "value": rr,
        "status": "GREEN" if rr >= 2.0 else ("YELLOW" if rr >= 1.5 else "RED"),
        "message": (
            f"R/R 1:{rr} — Good" if rr >= 2.0
            else f"R/R 1:{rr} — Acceptable minimum" if rr >= 1.5
            else f"R/R 1:{rr} — Unacceptable, do not trade"
        ),
    })

    checks.append({
        "category": "risk",
        "name": "Stop Distance",
        "value": stop_pct,
        "status": "GREEN" if stop_pct <= 4 else ("YELLOW" if stop_pct <= 6 else "RED"),
        "message": (
            f"Stop {stop_pct:.1f}% from entry — Tight" if stop_pct <= 4
            else f"Stop {stop_pct:.1f}% from entry — Manageable" if stop_pct <= 6
            else f"Stop {stop_pct:.1f}% from entry — Too wide for a short-term trade"
        ),
    })

    checks.append({
        "category": "risk",
        "name": "Position Size",
        "value": capital_pct,
        "status": "GREEN" if capital_pct <= 15 else ("YELLOW" if capital_pct <= 25 else "RED"),
        "message": (
            f"{capital_pct:.1f}% of capital — Fine" if capital_pct <= 15
            else f"{capital_pct:.1f}% of capital — High concentration" if capital_pct <= 25
            else f"{capital_pct:.1f}% of capital — Overexposed, reduce qty"
        ),
    })

    # --- Category D: Fundamentals ---
    val_score = s.get("valuation_score") or 0
    checks.append({
        "category": "fundamental",
        "name": "Valuation Score",
        "value": val_score,
        "status": "GREEN" if val_score >= 6 else ("YELLOW" if val_score >= 3 else "RED"),
        "message": f"Valuation score {val_score}/10",
    })

    promoter = f.get("promoter_holding")
    checks.append({
        "category": "fundamental",
        "name": "Promoter Holding",
        "value": promoter,
        "status": (
            "GREEN" if promoter and promoter >= 50
            else "YELLOW" if promoter and promoter >= 30
            else "RED"
        ),
        "message": (
            f"Promoter holding {promoter:.1f}%" if promoter
            else "Promoter data unavailable"
        ),
    })

    reds = [c for c in checks if c["status"] == "RED"]
    yellows = [c for c in checks if c["status"] == "YELLOW"]

    market_red = any(c["status"] == "RED" and c["category"] == "market" for c in checks)
    rr_red = any(c["status"] == "RED" and c["name"] == "Risk/Reward" for c in checks)

    if market_red:
        overall = "MARKET_UNFAVOURABLE"
    elif rr_red:
        overall = "POOR_RISK_REWARD"
    elif len(reds) > 0:
        overall = "HIGH_RISK"
    elif len(yellows) > 2:
        overall = "CAUTION"
    else:
        overall = "CLEAR"

    return {
        "ticker": ticker,
        "entry": entry,
        "stop_loss": stop,
        "target": target,
        "stop_pct": stop_pct,
        "risk_reward": rr,
        "qty": qty,
        "capital_deployed": round(capital_deployed, 2),
        "capital_pct": capital_pct,
        "overall": overall,
        "red_count": len(reds),
        "yellow_count": len(yellows),
        "checks": checks,
    }


@app.get("/api/trade/trades")
def get_active_trades():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT * FROM active_trades ORDER BY entry_date DESC"
        )).fetchall()
    return [dict(r._mapping) for r in rows]


@app.post("/api/trade/trades")
def add_trade(trade: dict):
    required = ["ticker", "entry_price", "stop_loss", "target_price", "qty"]
    for field in required:
        if field not in trade:
            raise HTTPException(status_code=400, detail=f"Missing field: {field}")

    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO active_trades
                (ticker, entry_price, stop_loss, target_price, qty,
                 capital_deployed, risk_amount, r_r, checklist_flags, notes)
            VALUES
                (:ticker, :entry_price, :stop_loss, :target_price, :qty,
                 :capital_deployed, :risk_amount, :r_r, :checklist_flags, :notes)
        """), {
            "ticker": trade["ticker"],
            "entry_price": trade["entry_price"],
            "stop_loss": trade["stop_loss"],
            "target_price": trade["target_price"],
            "qty": trade["qty"],
            "capital_deployed": trade.get("capital_deployed", 0),
            "risk_amount": trade.get("risk_amount", 0),
            "r_r": trade.get("r_r", 0),
            "checklist_flags": trade.get("checklist_flags", 0),
            "notes": trade.get("notes", ""),
        })
        conn.commit()

    return {"status": "ok", "message": f"Trade for {trade['ticker']} saved"}


@app.patch("/api/trade/trades/{trade_id}/close")
def close_trade(trade_id: int, body: dict):
    exit_price = body.get("exit_price")
    status = body.get("status", "CLOSED_MANUAL")
    if not exit_price:
        raise HTTPException(status_code=400, detail="exit_price is required")

    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT entry_price, qty FROM active_trades WHERE id = :id"
        ), {"id": trade_id}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Trade not found")

        pnl = round((exit_price - row[0]) * row[1], 2)
        conn.execute(text("""
            UPDATE active_trades SET
                exit_price = :exit_price,
                exit_date = NOW(),
                status = :status,
                pnl = :pnl
            WHERE id = :id
        """), {"exit_price": exit_price, "status": status, "pnl": pnl, "id": trade_id})
        conn.commit()

    return {"status": "ok", "pnl": pnl}