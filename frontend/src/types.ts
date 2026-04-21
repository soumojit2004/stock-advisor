export interface ScoreItem {
  ticker: string
  sector: string | null
  verdict: 'BUY' | 'WATCHLIST' | 'AVOID'
  final_score: number | null
  business_quality_score: number | null
  valuation_score: number | null
  technical_score: number | null
  entry_price: number | null
  target_price: number | null
  stop_loss: number | null
  risk_reward: number | null
  rsi: number | null
  price_vs_50dma: number | null
  price_vs_200dma: number | null
  pe_ratio: number | null
  roe: number | null
  roce: number | null
  revenue_growth_3yr: number | null
  net_profit_margin: number | null
  promoter_holding: number | null
  debt_to_equity: number | null
  watchlist: boolean
}

export interface SummaryResponse {
  total_scored: number
  buy_count: number
  watchlist_count: number
  avoid_count: number
  last_scored_at: string | null
}

export interface TradeSignal {
  ticker: string
  trade_score: number | null
  technical_score: number | null
  sentiment_score: number | null
  valuation_score: number | null
  verdict: string
  entry_price: number | null
  target_price: number | null
  stop_loss: number | null
  atr14: number | null
  risk_reward: number | null
  rsi: number | null
  ema20: number | null
  macd_signal: number | null
  volume_ratio: number | null
  near_52w_high: boolean
  price_vs_ema20_pct: number | null
  signal_type: string | null
  scored_at: string
}

export interface MarketSentiment {
  id: number
  india_vix: number
  nifty_close: number
  nifty_ema20: number
  nifty_ema50: number
  nifty_trend: string
  advance_decline: number
  sentiment_score: number
  market_regime: string
  updated_at: string
}

export interface ChecklistItem {
  category: string
  name: string
  value: number | string | null
  status: 'GREEN' | 'YELLOW' | 'RED'
  message: string
}

export interface ChecklistResponse {
  ticker: string
  entry: number
  stop_loss: number
  target: number
  stop_pct: number
  risk_reward: number
  qty: number
  capital_deployed: number
  capital_pct: number
  overall: string
  red_count: number
  yellow_count: number
  checks: ChecklistItem[]
}

export interface ActiveTrade {
  id: number
  ticker: string
  entry_price: number
  stop_loss: number
  target_price: number
  qty: number
  capital_deployed: number
  risk_amount: number
  r_r: number
  checklist_flags: number
  notes: string | null
  status: string
  entry_date: string
  exit_price: number | null
  exit_date: string | null
  pnl: number | null
}

export interface ScoreLookupResponse {
  invest: ScoreItem | null
  trade: TradeSignal | null
  error: string | null
}