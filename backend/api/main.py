"""FastAPI app exposing stock scores from PostgreSQL."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from os import getenv
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine, func, select
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
    allow_credentials=False,  # required when using allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)


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
