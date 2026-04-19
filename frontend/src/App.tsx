import axios from 'axios'
import { useEffect, useRef, useState } from 'react'
import type {
  ChecklistItem,
  ChecklistResponse,
  MarketSentiment,
  ScoreItem,
  SummaryResponse,
  TradeSignal,
} from './types'

const API_BASE = 'https://stock-advisor-sw3d.onrender.com'

type AppMode = 'INVEST' | 'TRADE'
type VerdictTab = 'BUY' | 'WATCHLIST' | 'AVOID'
type TradeTab = 'STRONG_BUY' | 'BUY' | 'WATCHLIST' | 'AVOID'

// ─── FORMATTERS ───────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined, decimals = 2): string {
  if (n === null || n === undefined) return '—'
  return n.toFixed(decimals)
}

function scoreBadgeClass(score: number | null): string {
  if (score === null) return 'bg-slate-700 text-slate-300'
  if (score >= 7) return 'bg-emerald-500/20 text-emerald-400'
  if (score >= 5.5) return 'bg-amber-500/20 text-amber-400'
  return 'bg-rose-500/20 text-rose-400'
}

function dmaTextClass(pct: number | null): string {
  if (pct === null) return 'text-slate-400'
  if (pct > 0) return 'text-emerald-400'
  if (pct < 0) return 'text-rose-400'
  return 'text-slate-300'
}

function rsiTextClass(rsi: number | null): string {
  if (rsi === null) return 'text-slate-400'
  if (rsi > 70) return 'text-rose-400'
  if (rsi < 30) return 'text-emerald-400'
  return 'text-white'
}

function vixColor(vix: number): string {
  if (vix < 15) return 'text-emerald-400'
  if (vix < 20) return 'text-amber-400'
  return 'text-rose-400'
}

function trendColor(trend: string): string {
  if (trend === 'BULLISH') return 'text-emerald-400'
  if (trend === 'NEUTRAL') return 'text-amber-400'
  return 'text-rose-400'
}

function regimeColor(regime: string): string {
  if (regime === 'TRENDING') return 'text-emerald-400'
  if (regime === 'CHOPPY') return 'text-amber-400'
  return 'text-rose-400'
}

function regimeRingClass(regime: string): string {
  if (regime === 'TRENDING') return 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/30'
  if (regime === 'CHOPPY') return 'bg-amber-500/15 text-amber-400 ring-amber-500/30'
  return 'bg-rose-500/15 text-rose-400 ring-rose-500/30'
}

// ─── SORT HELPERS ─────────────────────────────────────────────────────────────

type SortState<T> = { key: keyof T | null; dir: 'asc' | 'desc' }

function sortRows<T>(rows: T[], sort: SortState<T>): T[] {
  if (!sort.key) return rows
  return [...rows].sort((a, b) => {
    const av = (a[sort.key!] as unknown as number | string) ?? -Infinity
    const bv = (b[sort.key!] as unknown as number | string) ?? -Infinity
    if (av < bv) return sort.dir === 'asc' ? -1 : 1
    if (av > bv) return sort.dir === 'asc' ? 1 : -1
    return 0
  })
}

function toggleSort<T>(prev: SortState<T>, key: keyof T): SortState<T> {
  return {
    key,
    dir: prev.key === key && prev.dir === 'desc' ? 'asc' : 'desc',
  }
}

function SortIcon({ active, dir }: { active: boolean; dir: 'asc' | 'desc' }) {
  if (!active) return <span className="ml-1 text-slate-600">↕</span>
  return <span className="ml-1 text-emerald-400">{dir === 'desc' ? '↓' : '↑'}</span>
}

// ─── SMALL COMPONENTS ────────────────────────────────────────────────────────

function Spinner() {
  return (
    <div
      className="h-8 w-8 animate-spin rounded-full border-2 border-slate-600 border-t-slate-200"
      role="status"
      aria-label="Loading"
    />
  )
}

function VerdictBadge({ verdict }: { verdict: string }) {
  const config: Record<string, { cls: string; label: string }> = {
    STRONG_BUY: { cls: 'bg-emerald-500/25 text-emerald-300 ring-1 ring-emerald-500/40', label: '🟢 STRONG BUY' },
    BUY:        { cls: 'bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30', label: '🔵 BUY' },
    WATCHLIST:  { cls: 'bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/30',       label: '🟡 WATCHLIST' },
    AVOID:      { cls: 'bg-rose-500/15 text-rose-400 ring-1 ring-rose-500/30',          label: '🔴 AVOID' },
  }
  const c = config[verdict] ?? { cls: 'bg-slate-700 text-slate-300', label: verdict }
  return (
    <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-semibold ${c.cls}`}>
      {c.label}
    </span>
  )
}

function SignalTypeBadge({ type }: { type: string | null }) {
  if (!type) return <span className="text-slate-500">—</span>
  const cls: Record<string, string> = {
    BREAKOUT: 'bg-violet-500/15 text-violet-400',
    MOMENTUM: 'bg-blue-500/15 text-blue-400',
    INVEST:   'bg-slate-600/60 text-slate-300',
    NEUTRAL:  'bg-slate-700/80 text-slate-400',
  }
  return (
    <span className={`inline-flex rounded px-1.5 py-0.5 text-xs font-medium ${cls[type] ?? 'bg-slate-700 text-slate-400'}`}>
      {type}
    </span>
  )
}

function checkIcon(status: string): string {
  if (status === 'GREEN') return '🟢'
  if (status === 'YELLOW') return '🟡'
  return '🔴'
}

function overallBanner(overall: string): { bg: string; text: string; label: string } {
  switch (overall) {
    case 'CLEAR':               return { bg: 'bg-emerald-500/15 border-emerald-500/30', text: 'text-emerald-400', label: '✅ Clear to trade' }
    case 'CAUTION':             return { bg: 'bg-amber-500/15 border-amber-500/30',     text: 'text-amber-400',   label: '⚠️ Proceed with caution' }
    case 'HIGH_RISK':           return { bg: 'bg-rose-500/15 border-rose-500/30',       text: 'text-rose-400',    label: '🚨 High risk — review all flags' }
    case 'POOR_RISK_REWARD':    return { bg: 'bg-rose-500/15 border-rose-500/30',       text: 'text-rose-400',    label: '🚫 Poor risk/reward — do not trade' }
    case 'MARKET_UNFAVOURABLE': return { bg: 'bg-rose-500/15 border-rose-500/30',       text: 'text-rose-400',    label: '🌧️ Market unfavourable — avoid new entries' }
    default:                    return { bg: 'bg-slate-700/50 border-slate-600',        text: 'text-slate-400',   label: overall }
  }
}

// ─── BUILD SIGNAL FROM SCOREITEM ─────────────────────────────────────────────

function scoreItemToSignal(row: ScoreItem): TradeSignal {
  return {
    ticker: row.ticker,
    trade_score: row.final_score,
    technical_score: row.technical_score,
    sentiment_score: null,
    valuation_score: row.valuation_score,
    verdict: row.verdict,
    entry_price: row.entry_price,
    target_price: row.target_price,
    stop_loss: row.stop_loss,
    atr14: null,
    risk_reward: row.risk_reward,
    rsi: row.rsi,
    ema20: null,
    macd_signal: null,
    volume_ratio: null,
    near_52w_high: false,
    price_vs_ema20_pct: null,
    signal_type: 'INVEST',
    scored_at: new Date().toISOString(),
  }
}

// ─── SENTIMENT BAR ────────────────────────────────────────────────────────────

function SentimentBar({ sentiment }: { sentiment: MarketSentiment }) {
  const time = new Date(sentiment.updated_at).toLocaleTimeString('en-IN', {
    hour: '2-digit', minute: '2-digit',
  })
  return (
    <div className="mb-4 rounded-lg border border-slate-700/80 bg-slate-900/60 px-4 py-3 space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs font-semibold uppercase tracking-widest text-slate-500">Market</span>
        <span className={`text-sm font-semibold ${regimeColor(sentiment.market_regime)}`}>
          {sentiment.market_regime}
        </span>
        <span className="text-slate-700">|</span>
        <span className="text-xs text-slate-400">
          VIX{' '}
          <span className={`font-semibold ${vixColor(sentiment.india_vix)}`}>
            {sentiment.india_vix.toFixed(1)}
          </span>
          <span className="ml-1 text-slate-500">
            ({sentiment.india_vix < 15 ? 'Calm' : sentiment.india_vix < 20 ? 'Elevated' : 'High'})
          </span>
        </span>
        <span className="text-slate-700">|</span>
        <span className="text-xs text-slate-400">
          Nifty{' '}
          <span className={`font-semibold ${trendColor(sentiment.nifty_trend)}`}>
            {sentiment.nifty_trend}
          </span>
        </span>
        <span className="text-slate-700">|</span>
        <span className="text-xs text-slate-400">
          Sentiment <span className="font-semibold text-white">{sentiment.sentiment_score}/10</span>
        </span>
        <span className="ml-auto text-xs text-slate-600">Updated {time}</span>
      </div>
      {sentiment.sentiment_score < 5 && (
        <div className="rounded border border-rose-500/30 bg-rose-950/30 px-3 py-2 text-xs text-rose-400">
          ⚠️ Market conditions unfavourable. All signals carry elevated risk — trade smaller or wait.
        </div>
      )}
    </div>
  )
}

// ─── CHECKLIST PANEL ─────────────────────────────────────────────────────────

function ChecklistPanel({
  ticker,
  price,
  capital,
}: {
  ticker: string
  price: number
  capital: number
}) {
  const [data, setData] = useState<ChecklistResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [notInTradeUniverse, setNotInTradeUniverse] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!price || price <= 0) { setData(null); return }
    if (timerRef.current) clearTimeout(timerRef.current)
    setLoading(true)
    setNotInTradeUniverse(false)
    timerRef.current = setTimeout(() => {
      axios
        .get<ChecklistResponse>(`${API_BASE}/api/trade/checklist/${ticker}`, {
          params: { price, capital },
        })
        .then((res) => setData(res.data))
        .catch((err) => {
          if (axios.isAxiosError(err) && err.response?.status === 404) {
            setNotInTradeUniverse(true)
          }
          setData(null)
        })
        .finally(() => setLoading(false))
    }, 700)
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [ticker, price, capital])

  if (!price || price <= 0) {
    return <p className="text-xs text-slate-600">Enter a price above to run the checklist.</p>
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-3 text-xs text-slate-500">
        <div className="h-3.5 w-3.5 animate-spin rounded-full border border-slate-500 border-t-slate-300" />
        Running checklist...
      </div>
    )
  }

  if (notInTradeUniverse) {
    return (
      <div className="rounded-lg border border-slate-700/60 bg-slate-800/40 px-4 py-3">
        <p className="text-xs font-medium text-slate-400">ℹ️ Full checklist unavailable</p>
        <p className="mt-1 text-xs text-slate-500">
          This stock is below the trade mode liquidity threshold (avg daily volume &lt; ₹10cr).
          Validate market conditions and risk parameters manually before entering.
        </p>
      </div>
    )
  }

  if (!data) return null

  const banner = overallBanner(data.overall)
  const categories = [
    { key: 'market',      label: 'Market Conditions' },
    { key: 'technical',   label: 'Technicals' },
    { key: 'risk',        label: 'Risk Parameters' },
    { key: 'fundamental', label: 'Fundamentals' },
  ]

  return (
    <div className="space-y-3">
      <div className={`rounded-lg border px-4 py-3 ${banner.bg}`}>
        <p className={`text-sm font-semibold ${banner.text}`}>{banner.label}</p>
        {(data.red_count > 0 || data.yellow_count > 0) && (
          <p className="mt-0.5 text-xs text-slate-400">
            {data.red_count} red flag{data.red_count !== 1 ? 's' : ''},{' '}
            {data.yellow_count} warning{data.yellow_count !== 1 ? 's' : ''}
          </p>
        )}
      </div>
      {categories.map((cat) => {
        const catChecks = data.checks.filter((c: ChecklistItem) => c.category === cat.key)
        if (catChecks.length === 0) return null
        return (
          <div key={cat.key}>
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-widest text-slate-500">
              {cat.label}
            </p>
            <div className="space-y-1">
              {catChecks.map((check: ChecklistItem, i: number) => (
                <div key={i} className="flex items-start gap-2 rounded-md bg-slate-800/60 px-3 py-2">
                  <span className="mt-px text-xs">{checkIcon(check.status)}</span>
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-slate-300">{check.name}</p>
                    <p className="text-xs text-slate-500">{check.message}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─── ADD TRADE DRAWER ─────────────────────────────────────────────────────────

function AddTradeDrawer({
  signal,
  onClose,
  onSaved,
}: {
  signal: TradeSignal
  onClose: () => void
  onSaved: () => void
}) {
  const isInvestMode = signal.signal_type === 'INVEST'
  const [price, setPrice] = useState<string>(signal.entry_price?.toFixed(2) ?? '')
  const [capital, setCapital] = useState<string>('500000')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const priceNum   = parseFloat(price) || 0
  const capitalNum = parseFloat(capital) || 500000
  const atr        = signal.atr14 ?? 0

  let stopLoss: number
  let target: number

  if (atr > 0 && priceNum > 0) {
    stopLoss = priceNum - 1.5 * atr
    target   = priceNum + 2.0 * atr
  } else if (signal.stop_loss && signal.target_price && signal.entry_price && priceNum > 0) {
    const delta = priceNum - signal.entry_price
    stopLoss = signal.stop_loss + delta
    target   = signal.target_price + delta
  } else {
    stopLoss = priceNum * 0.93
    target   = priceNum * 1.15
  }

  const stopPct     = priceNum > 0 ? ((priceNum - stopLoss) / priceNum * 100) : 0
  const rr          = (priceNum - stopLoss) > 0 ? (target - priceNum) / (priceNum - stopLoss) : 0
  const riskAmt     = capitalNum * 0.01
  const qty         = (priceNum - stopLoss) > 0 ? Math.floor(riskAmt / (priceNum - stopLoss)) : 0
  const deployed    = qty * priceNum
  const deployedPct = capitalNum > 0 ? (deployed / capitalNum * 100) : 0

  async function handleSave() {
    if (!priceNum || priceNum <= 0 || qty === 0) return
    setSaving(true)
    setSaveError(null)
    try {
      await axios.post(`${API_BASE}/api/trade/trades`, {
        ticker: signal.ticker,
        entry_price: priceNum,
        stop_loss: parseFloat(stopLoss.toFixed(2)),
        target_price: parseFloat(target.toFixed(2)),
        qty,
        capital_deployed: parseFloat(deployed.toFixed(2)),
        risk_amount: parseFloat(riskAmt.toFixed(2)),
        r_r: parseFloat(rr.toFixed(2)),
        notes,
      })
      onSaved()
      onClose()
    } catch {
      setSaveError('Failed to save trade. Try again.')
    } finally {
      setSaving(false)
    }
  }

  const displayTicker = signal.ticker.replace('.NS', '')

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col overflow-y-auto border-l border-slate-700/80 bg-slate-900 shadow-2xl">

        <div className="flex items-center justify-between border-b border-slate-700/80 px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-white">Add a Trade</h2>
            <p className="text-xs text-slate-400">
              {displayTicker}
              {signal.signal_type && (
                <span className={`ml-2 rounded px-1.5 py-0.5 text-xs font-medium ${
                  isInvestMode ? 'bg-slate-600/60 text-slate-300' : 'bg-violet-500/15 text-violet-400'
                }`}>
                  {signal.signal_type}
                </span>
              )}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-slate-400 transition hover:bg-slate-800 hover:text-white"
          >
            ✕
          </button>
        </div>

        {isInvestMode && (
          <div className="border-b border-slate-700/60 bg-slate-800/40 px-5 py-3">
            <p className="text-xs text-slate-400">
              📈 Using <span className="font-medium text-white">invest mode</span> stop/target (50 DMA based).
              Stop and target shift proportionally if you enter a different price.
            </p>
          </div>
        )}

        <div className="flex-1 space-y-5 px-5 py-5">
          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-slate-500">
              Current Market Price (₹)
            </label>
            <input
              type="number"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              placeholder={signal.entry_price?.toFixed(2)}
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:border-emerald-500/50 focus:outline-none"
            />
            <p className="mt-1 text-xs text-slate-500">
              Signal entry: ₹{signal.entry_price?.toFixed(2)}
              {!isInvestMode && signal.atr14 && (
                <span className="ml-2">ATR14: {signal.atr14.toFixed(2)}</span>
              )}
            </p>
          </div>

          {priceNum > 0 && (
            <div className="rounded-lg border border-slate-700/80 bg-slate-800/50 p-4">
              <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-500">
                Auto-calculated
              </p>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Stop Loss</span>
                  <span className="font-medium text-rose-400">
                    ₹{stopLoss.toFixed(2)}{' '}
                    <span className="text-xs text-slate-500">(-{stopPct.toFixed(1)}%)</span>
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Target</span>
                  <span className="font-medium text-emerald-400">₹{target.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Risk/Reward</span>
                  <span className={`font-medium ${rr >= 2 ? 'text-emerald-400' : rr >= 1.5 ? 'text-amber-400' : 'text-rose-400'}`}>
                    1 : {rr.toFixed(2)}
                  </span>
                </div>
                <div className="my-1 border-t border-slate-700/60" />
                <div className="flex items-center justify-between">
                  <label className="text-xs text-slate-400">Capital (₹)</label>
                  <input
                    type="number"
                    value={capital}
                    onChange={(e) => setCapital(e.target.value)}
                    className="w-36 rounded border border-slate-600 bg-slate-700 px-2 py-1 text-xs text-white focus:border-emerald-500/50 focus:outline-none"
                  />
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-slate-400">Risk per trade (1%)</span>
                  <span className="text-slate-300">
                    ₹{riskAmt.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                  </span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-slate-400">Suggested qty</span>
                  <span className="font-semibold text-white">{qty} shares</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-slate-400">Capital deployed</span>
                  <span className={
                    deployedPct > 25 ? 'font-medium text-rose-400' :
                    deployedPct > 15 ? 'text-amber-400' : 'text-slate-300'
                  }>
                    ₹{deployed.toLocaleString('en-IN', { maximumFractionDigits: 0 })}{' '}
                    <span className="text-slate-500">({deployedPct.toFixed(1)}%)</span>
                  </span>
                </div>
              </div>
            </div>
          )}

          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-slate-500">
              Pre-Trade Checklist
            </p>
            <ChecklistPanel ticker={signal.ticker} price={priceNum} capital={capitalNum} />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-slate-500">
              Notes (optional)
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder="Why are you taking this trade?"
              className="w-full resize-none rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-emerald-500/50 focus:outline-none"
            />
          </div>

          {saveError && <p className="text-xs text-rose-400">{saveError}</p>}
        </div>

        <div className="flex gap-3 border-t border-slate-700/80 px-5 py-4">
          <button
            onClick={handleSave}
            disabled={saving || priceNum <= 0 || qty === 0}
            className="flex-1 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {saving ? 'Saving...' : 'Save Trade'}
          </button>
          <button
            onClick={onClose}
            className="rounded-lg border border-slate-700 px-4 py-2.5 text-sm text-slate-400 transition hover:text-white"
          >
            Cancel
          </button>
        </div>
      </div>
    </>
  )
}

// ─── MAIN APP ─────────────────────────────────────────────────────────────────

export default function App() {
  const [mode, setMode] = useState<AppMode>('INVEST')

  // Invest mode state
  const [summary, setSummary] = useState<SummaryResponse | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(true)
  const [summaryError, setSummaryError] = useState<string | null>(null)
  const [allScores, setAllScores] = useState<Record<VerdictTab, ScoreItem[]>>({
    BUY: [], WATCHLIST: [], AVOID: [],
  })
  const [scoresLoading, setScoresLoading] = useState(true)
  const [scoresError, setScoresError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<VerdictTab>('BUY')
  const [investSort, setInvestSort] = useState<SortState<ScoreItem>>({ key: null, dir: 'desc' })

  // Trade mode state
  const [sentiment, setSentiment] = useState<MarketSentiment | null>(null)
  const [sentimentLoading, setSentimentLoading] = useState(false)
  const [allTradeSignals, setAllTradeSignals] = useState<Record<TradeTab, TradeSignal[]>>({
    STRONG_BUY: [], BUY: [], WATCHLIST: [], AVOID: [],
  })
  const [tradeLoading, setTradeLoading] = useState(false)
  const [tradeError, setTradeError] = useState<string | null>(null)
  const [tradeTab, setTradeTab] = useState<TradeTab>('BUY')
  const [tradeDataLoaded, setTradeDataLoaded] = useState(false)
  const [tradeSort, setTradeSort] = useState<SortState<TradeSignal>>({ key: null, dir: 'desc' })

  // Shared drawer state
  const [addTradeSignal, setAddTradeSignal] = useState<TradeSignal | null>(null)
  const [fetchingSignal, setFetchingSignal] = useState<string | null>(null)
  const [tradeSaved, setTradeSaved] = useState(false)

  useEffect(() => {
    let cancelled = false
    setSummaryLoading(true)
    axios
      .get<SummaryResponse>(`${API_BASE}/api/summary`)
      .then((res) => { if (!cancelled) setSummary(res.data) })
      .catch(() => { if (!cancelled) setSummaryError('Failed to load summary') })
      .finally(() => { if (!cancelled) setSummaryLoading(false) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    let cancelled = false
    setScoresLoading(true)
    Promise.all([
      axios.get<ScoreItem[]>(`${API_BASE}/api/scores`, { params: { verdict: 'BUY' } }),
      axios.get<ScoreItem[]>(`${API_BASE}/api/scores`, { params: { verdict: 'WATCHLIST' } }),
      axios.get<ScoreItem[]>(`${API_BASE}/api/scores`, { params: { verdict: 'AVOID' } }),
    ])
      .then(([buy, watchlist, avoid]) => {
        if (!cancelled) setAllScores({ BUY: buy.data, WATCHLIST: watchlist.data, AVOID: avoid.data })
      })
      .catch(() => { if (!cancelled) setScoresError('Failed to load scores') })
      .finally(() => { if (!cancelled) setScoresLoading(false) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (mode !== 'TRADE' || tradeDataLoaded) return
    let cancelled = false

    setSentimentLoading(true)
    axios
      .get<MarketSentiment>(`${API_BASE}/api/trade/sentiment`)
      .then((res) => { if (!cancelled) setSentiment(res.data) })
      .finally(() => { if (!cancelled) setSentimentLoading(false) })

    setTradeLoading(true)
    setTradeError(null)
    Promise.all([
      axios.get<TradeSignal[]>(`${API_BASE}/api/trade/scores`, { params: { verdict: 'STRONG_BUY' } }),
      axios.get<TradeSignal[]>(`${API_BASE}/api/trade/scores`, { params: { verdict: 'BUY' } }),
      axios.get<TradeSignal[]>(`${API_BASE}/api/trade/scores`, { params: { verdict: 'WATCHLIST' } }),
      axios.get<TradeSignal[]>(`${API_BASE}/api/trade/scores`, { params: { verdict: 'AVOID' } }),
    ])
      .then(([sb, buy, wl, avoid]) => {
        if (!cancelled) {
          setAllTradeSignals({
            STRONG_BUY: sb.data, BUY: buy.data,
            WATCHLIST: wl.data, AVOID: avoid.data,
          })
          setTradeDataLoaded(true)
        }
      })
      .catch(() => { if (!cancelled) setTradeError('Failed to load trade signals') })
      .finally(() => { if (!cancelled) setTradeLoading(false) })

    return () => { cancelled = true }
  }, [mode, tradeDataLoaded])

  async function handleInvestAdd(row: ScoreItem) {
    setFetchingSignal(row.ticker)
    setTradeSaved(false)
    try {
      const res = await axios.get<TradeSignal>(`${API_BASE}/api/trade/scores/${row.ticker}`)
      setAddTradeSignal(res.data)
    } catch {
      setAddTradeSignal(scoreItemToSignal(row))
    } finally {
      setFetchingSignal(null)
    }
  }

  const investScores = sortRows(allScores[activeTab], investSort)
  const tradeSignals = sortRows(allTradeSignals[tradeTab], tradeSort)
  const investTabs: VerdictTab[] = ['BUY', 'WATCHLIST', 'AVOID']
  const tradeTabs: TradeTab[]    = ['STRONG_BUY', 'BUY', 'WATCHLIST', 'AVOID']

  const investColumns: { label: string; key: keyof ScoreItem }[] = [
    { label: 'Ticker',        key: 'ticker' },
    { label: 'Sector',        key: 'sector' },
    { label: 'Score',         key: 'final_score' },
    { label: 'Quality',       key: 'business_quality_score' },
    { label: 'Valuation',     key: 'valuation_score' },
    { label: 'Technical',     key: 'technical_score' },
    { label: 'Entry (₹)',     key: 'entry_price' },
    { label: 'Target (₹)',    key: 'target_price' },
    { label: 'Stop Loss (₹)', key: 'stop_loss' },
    { label: 'R/R',           key: 'risk_reward' },
    { label: 'RSI',           key: 'rsi' },
    { label: 'vs 50DMA',      key: 'price_vs_50dma' },
    { label: 'vs 200DMA',     key: 'price_vs_200dma' },
    { label: 'ROE%',          key: 'roe' },
    { label: 'Rev Growth%',   key: 'revenue_growth_3yr' },
    { label: 'Promoter%',     key: 'promoter_holding' },
  ]

  const tradeColumns: { label: string; key: keyof TradeSignal | '' }[] = [
    { label: 'Ticker',     key: 'ticker' },
    { label: 'Signal',     key: 'verdict' },
    { label: 'Type',       key: 'signal_type' },
    { label: 'Score',      key: 'trade_score' },
    { label: 'Technical',  key: 'technical_score' },
    { label: 'Entry (₹)',  key: 'entry_price' },
    { label: 'Target (₹)', key: 'target_price' },
    { label: 'Stop (₹)',   key: 'stop_loss' },
    { label: 'R/R',        key: 'risk_reward' },
    { label: 'RSI',        key: 'rsi' },
    { label: 'Vol Ratio',  key: 'volume_ratio' },
    { label: 'ATR14',      key: 'atr14' },
    { label: '',           key: '' },
  ]

  return (
    <div className="flex min-h-screen flex-col bg-[#0f172a] text-slate-200">

      {/* ── NAV ── */}
      <nav className="border-b border-slate-700/80 bg-slate-900/50 px-4 py-4 sm:px-6">
        <div className="mx-auto flex w-full flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <div className="flex flex-col gap-0.5">
              <h1 className="text-left text-xl font-semibold tracking-tight text-white">Stock Advisor</h1>
              <p className="text-xs text-slate-500">
                made with 🧡 by <span className="text-[#FF6E00]">Syro</span>
              </p>
            </div>
            <div className="ml-2 flex rounded-lg bg-slate-800 p-0.5 ring-1 ring-slate-700">
              {(['INVEST', 'TRADE'] as AppMode[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMode(m)}
                  className={`rounded-md px-4 py-1.5 text-xs font-semibold transition ${
                    mode === m ? 'bg-slate-600 text-white shadow' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {m === 'INVEST' ? '📈 INVEST' : '⚡ TRADE'}
                </button>
              ))}
            </div>
          </div>

          {mode === 'INVEST' && (
            <div className="flex flex-wrap items-center gap-2 lg:justify-end">
              {summaryLoading ? <Spinner /> : summaryError ? (
                <span className="text-sm text-rose-400">{summaryError}</span>
              ) : summary ? (
                <>
                  <span className="rounded-full bg-slate-700/80 px-3 py-1 text-sm text-slate-200">
                    Total <span className="font-semibold text-white">{summary.total_scored}</span>
                  </span>
                  <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-sm text-emerald-400 ring-1 ring-emerald-500/30">
                    BUY <span className="font-semibold">{summary.buy_count}</span>
                  </span>
                  <span className="rounded-full bg-amber-500/15 px-3 py-1 text-sm text-amber-400 ring-1 ring-amber-500/30">
                    WATCHLIST <span className="font-semibold">{summary.watchlist_count}</span>
                  </span>
                  <span className="rounded-full bg-rose-500/15 px-3 py-1 text-sm text-rose-400 ring-1 ring-rose-500/30">
                    AVOID <span className="font-semibold">{summary.avoid_count}</span>
                  </span>
                </>
              ) : null}
            </div>
          )}

          {mode === 'TRADE' && sentiment && (
            <div className="flex flex-wrap items-center gap-2 lg:justify-end">
              <span className={`rounded-full px-3 py-1 text-sm font-semibold ring-1 ${regimeRingClass(sentiment.market_regime)}`}>
                {sentiment.market_regime}
              </span>
              <span className="rounded-full bg-slate-700/80 px-3 py-1 text-sm text-slate-300">
                VIX <span className={`font-semibold ${vixColor(sentiment.india_vix)}`}>{sentiment.india_vix.toFixed(1)}</span>
              </span>
              <span className="rounded-full bg-slate-700/80 px-3 py-1 text-sm text-slate-300">
                Nifty <span className={`font-semibold ${trendColor(sentiment.nifty_trend)}`}>{sentiment.nifty_trend}</span>
              </span>
            </div>
          )}
        </div>
      </nav>

      {/* ── MAIN ── */}
      <div className="mx-auto w-full flex-1 px-4 py-6 sm:px-6">

        {/* ── INVEST MODE ── */}
        {mode === 'INVEST' && (
          <>
            <div className="mb-6 flex gap-1 rounded-lg bg-slate-800/80 p-1 ring-1 ring-slate-700/80">
              {investTabs.map((tab) => (
                <button key={tab} type="button"
                  onClick={() => { setActiveTab(tab); setInvestSort({ key: null, dir: 'desc' }) }}
                  className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition sm:flex-none sm:px-6 ${
                    activeTab === tab ? 'bg-slate-700 text-white shadow' : 'text-slate-400 hover:text-white'
                  }`}
                >{tab}</button>
              ))}
            </div>

            {scoresError && (
              <div className="mb-4 rounded-lg border border-rose-500/40 bg-rose-950/40 px-4 py-3 text-sm text-rose-300">
                {scoresError}
              </div>
            )}

            {tradeSaved && (
              <div className="mb-4 rounded-lg border border-emerald-500/40 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
                ✅ Trade saved successfully.
              </div>
            )}

            <div className="overflow-hidden rounded-xl bg-slate-900/40">
              {scoresLoading ? (
                <div className="flex min-h-[240px] flex-col items-center justify-center gap-3 py-16">
                  <Spinner />
                  <p className="animate-pulse text-xs text-slate-500">Loading stocks — may take a moment on first load...</p>
                </div>
              ) : investScores.length === 0 ? (
                <div className="flex min-h-[240px] flex-col items-center justify-center gap-2 py-16 text-slate-500">
                  <p className="text-lg font-medium text-slate-400">No stocks</p>
                  <p className="text-sm">Nothing matched this tab.</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-700 bg-slate-900/80 uppercase tracking-wide text-slate-400">
                        {investColumns.map(({ label, key }) => (
                          <th
                            key={key}
                            onClick={() => setInvestSort(prev => toggleSort(prev, key))}
                            className="whitespace-nowrap px-2 py-2 font-medium cursor-pointer select-none hover:text-white"
                          >
                            {label}<SortIcon active={investSort.key === key} dir={investSort.dir} />
                          </th>
                        ))}
                        <th className="whitespace-nowrap px-2 py-2 font-medium" />
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-700/60">
                      {investScores.map((row) => (
                        <tr key={row.ticker} className="hover:bg-slate-800/50">
                          <td className="whitespace-nowrap px-2 py-2 font-bold text-white">{row.ticker}</td>
                          <td className="max-w-[120px] truncate px-2 py-2 text-slate-300">{row.sector ?? '—'}</td>
                          <td className="whitespace-nowrap px-2 py-2">
                            <span className={`inline-flex min-w-[3rem] justify-center rounded-md px-2 py-0.5 text-xs font-semibold ${scoreBadgeClass(row.final_score)}`}>
                              {fmt(row.final_score)}
                            </span>
                          </td>
                          <td className="whitespace-nowrap px-2 py-2 tabular-nums text-slate-300">{fmt(row.business_quality_score)}</td>
                          <td className="whitespace-nowrap px-2 py-2 tabular-nums text-slate-300">{fmt(row.valuation_score)}</td>
                          <td className="whitespace-nowrap px-2 py-2 tabular-nums text-slate-300">{fmt(row.technical_score)}</td>
                          <td className="whitespace-nowrap px-2 py-2 tabular-nums text-slate-300">{fmt(row.entry_price)}</td>
                          <td className="whitespace-nowrap px-2 py-2 tabular-nums text-emerald-400">{fmt(row.target_price)}</td>
                          <td className="whitespace-nowrap px-2 py-2 tabular-nums text-slate-300">{fmt(row.stop_loss)}</td>
                          <td className="whitespace-nowrap px-2 py-2 tabular-nums text-slate-300">{fmt(row.risk_reward)}</td>
                          <td className={`whitespace-nowrap px-2 py-2 tabular-nums ${rsiTextClass(row.rsi)}`}>{fmt(row.rsi)}</td>
                          <td className={`whitespace-nowrap px-2 py-2 tabular-nums ${dmaTextClass(row.price_vs_50dma)}`}>{fmt(row.price_vs_50dma)}</td>
                          <td className={`whitespace-nowrap px-2 py-2 tabular-nums ${dmaTextClass(row.price_vs_200dma)}`}>{fmt(row.price_vs_200dma)}</td>
                          <td className="whitespace-nowrap px-2 py-2 tabular-nums text-slate-300">{fmt(row.roe)}</td>
                          <td className="whitespace-nowrap px-2 py-2 tabular-nums text-slate-300">{fmt(row.revenue_growth_3yr)}</td>
                          <td className="whitespace-nowrap px-2 py-2 tabular-nums text-slate-300">{fmt(row.promoter_holding)}</td>
                          <td className="whitespace-nowrap px-2 py-2">
                            <button
                              type="button"
                              onClick={() => handleInvestAdd(row)}
                              disabled={fetchingSignal === row.ticker}
                              className="rounded-md bg-slate-700/60 px-3 py-1 text-xs font-semibold text-slate-300 ring-1 ring-slate-600 transition hover:bg-slate-600 hover:text-white disabled:opacity-40"
                            >
                              {fetchingSignal === row.ticker ? '...' : '+ Add'}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}

        {/* ── TRADE MODE ── */}
        {mode === 'TRADE' && (
          <>
            {sentimentLoading ? (
              <div className="mb-4 flex items-center gap-2 text-xs text-slate-500">
                <div className="h-3 w-3 animate-spin rounded-full border border-slate-600 border-t-slate-300" />
                Loading market data...
              </div>
            ) : sentiment ? (
              <SentimentBar sentiment={sentiment} />
            ) : null}

            <div className="mb-6 flex gap-1 rounded-lg bg-slate-800/80 p-1 ring-1 ring-slate-700/80">
              {tradeTabs.map((tab) => (
                <button key={tab} type="button"
                  onClick={() => { setTradeTab(tab); setTradeSort({ key: null, dir: 'desc' }) }}
                  className={`flex-1 rounded-md px-3 py-2 text-xs font-semibold transition sm:flex-none sm:px-5 ${
                    tradeTab === tab ? 'bg-slate-700 text-white shadow' : 'text-slate-400 hover:text-white'
                  }`}
                >{tab.replace('_', ' ')}</button>
              ))}
            </div>

            {tradeError && (
              <div className="mb-4 rounded-lg border border-rose-500/40 bg-rose-950/40 px-4 py-3 text-sm text-rose-300">
                {tradeError}
              </div>
            )}

            {tradeSaved && (
              <div className="mb-4 rounded-lg border border-emerald-500/40 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
                ✅ Trade saved successfully.
              </div>
            )}

            <div className="overflow-hidden rounded-xl bg-slate-900/40">
              {tradeLoading ? (
                <div className="flex min-h-[240px] flex-col items-center justify-center gap-3 py-16">
                  <Spinner />
                  <p className="animate-pulse text-xs text-slate-500">Loading trade signals...</p>
                </div>
              ) : tradeSignals.length === 0 ? (
                <div className="flex min-h-[240px] flex-col items-center justify-center gap-2 py-16 text-slate-500">
                  <p className="text-lg font-medium text-slate-400">No signals</p>
                  <p className="text-sm">No stocks in this category right now.</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-700 bg-slate-900/80 uppercase tracking-wide text-slate-400">
                        {tradeColumns.map(({ label, key }) => (
                          <th
                            key={key || '__action'}
                            onClick={() => key && setTradeSort(prev => toggleSort(prev, key as keyof TradeSignal))}
                            className={`whitespace-nowrap px-2 py-2 font-medium select-none ${key ? 'cursor-pointer hover:text-white' : ''}`}
                          >
                            {label}
                            {key && <SortIcon active={tradeSort.key === key} dir={tradeSort.dir} />}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-700/60">
                      {tradeSignals.map((row) => (
                        <tr key={row.ticker} className="hover:bg-slate-800/50">
                          <td className="whitespace-nowrap px-2 py-2 font-bold text-white">{row.ticker.replace('.NS', '')}</td>
                          <td className="whitespace-nowrap px-2 py-2"><VerdictBadge verdict={row.verdict} /></td>
                          <td className="whitespace-nowrap px-2 py-2"><SignalTypeBadge type={row.signal_type} /></td>
                          <td className="whitespace-nowrap px-2 py-2">
                            <span className={`inline-flex min-w-[3rem] justify-center rounded-md px-2 py-0.5 text-xs font-semibold ${scoreBadgeClass(row.trade_score)}`}>
                              {fmt(row.trade_score)}
                            </span>
                          </td>
                          <td className="whitespace-nowrap px-2 py-2 tabular-nums text-slate-300">{fmt(row.technical_score)}</td>
                          <td className="whitespace-nowrap px-2 py-2 tabular-nums text-slate-300">{fmt(row.entry_price)}</td>
                          <td className="whitespace-nowrap px-2 py-2 tabular-nums text-emerald-400">{fmt(row.target_price)}</td>
                          <td className="whitespace-nowrap px-2 py-2 tabular-nums text-rose-400">{fmt(row.stop_loss)}</td>
                          <td className="whitespace-nowrap px-2 py-2 tabular-nums text-slate-300">{fmt(row.risk_reward)}</td>
                          <td className={`whitespace-nowrap px-2 py-2 tabular-nums ${rsiTextClass(row.rsi)}`}>{fmt(row.rsi)}</td>
                          <td className="whitespace-nowrap px-2 py-2 tabular-nums text-slate-300">{fmt(row.volume_ratio)}</td>
                          <td className="whitespace-nowrap px-2 py-2 tabular-nums text-slate-300">{fmt(row.atr14)}</td>
                          <td className="whitespace-nowrap px-2 py-2">
                            <button
                              type="button"
                              onClick={() => { setAddTradeSignal(row); setTradeSaved(false) }}
                              className="rounded-md bg-emerald-600/20 px-3 py-1 text-xs font-semibold text-emerald-400 ring-1 ring-emerald-500/30 transition hover:bg-emerald-600/40"
                            >
                              + Add
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* ── FOOTER ── */}
      <footer className="mt-6 border-t border-slate-700/80 bg-slate-900/50 px-4 py-4 sm:px-6">
        <div className="mx-auto w-full flex items-center justify-between">
          <div className="flex items-center gap-4">
            <span className="text-xs text-slate-500">Check out:</span>
            <a href="https://www.instagram.com/syro.ig/" target="_blank" rel="noopener noreferrer"
              className="text-xs font-medium text-slate-300 underline underline-offset-2 transition-colors hover:text-white">
              Instagram
            </a>
            <a href="https://www.linkedin.com/in/soumojitg" target="_blank" rel="noopener noreferrer"
              className="text-xs font-medium text-slate-300 underline underline-offset-2 transition-colors hover:text-white">
              LinkedIn
            </a>
          </div>
          <a href="https://docs.google.com/document/d/1Q_yVIUlCQjCcxXt-6Rj_oQOKghdG44gqPYHC2Qk8KI4/edit?usp=sharing"
            target="_blank" rel="noopener noreferrer"
            className="text-xs font-medium text-slate-300 underline underline-offset-2 transition-colors hover:text-white">
            How to Use
          </a>
        </div>
      </footer>

      {addTradeSignal && (
        <AddTradeDrawer
          signal={addTradeSignal}
          onClose={() => setAddTradeSignal(null)}
          onSaved={() => setTradeSaved(true)}
        />
      )}
    </div>
  )
}