export interface ScoreItem {
  ticker: string
  sector: string | null
  verdict: 'BUY' | 'WATCHLIST' | 'AVOID'
  final_score: number | null
  business_quality_score: number | null
  valuation_score: number | null
  technical_score: number | null
  entry_price: number | null
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
