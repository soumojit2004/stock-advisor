import axios from 'axios'
import { useEffect, useState } from 'react'
import type { ScoreItem, SummaryResponse } from './types'

const API_BASE = 'https://stock-advisor-sw3d.onrender.com'

type VerdictTab = 'BUY' | 'WATCHLIST' | 'AVOID'

function fmt(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  return n.toFixed(2)
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

function Spinner() {
  return (
    <div
      className="h-8 w-8 animate-spin rounded-full border-2 border-slate-600 border-t-slate-200"
      role="status"
      aria-label="Loading"
    />
  )
}

export default function App() {
  const [summary, setSummary] = useState<SummaryResponse | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(true)
  const [summaryError, setSummaryError] = useState<string | null>(null)

  const [scores, setScores] = useState<ScoreItem[]>([])
  const [scoresLoading, setScoresLoading] = useState(true)
  const [scoresError, setScoresError] = useState<string | null>(null)

  const [activeTab, setActiveTab] = useState<VerdictTab>('BUY')

  useEffect(() => {
    let cancelled = false
    setSummaryLoading(true)
    setSummaryError(null)
    axios
      .get<SummaryResponse>(`${API_BASE}/api/summary`)
      .then((res) => {
        if (!cancelled) setSummary(res.data)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const msg = axios.isAxiosError(err)
            ? (err.response?.data as { detail?: string } | undefined)?.detail ??
              err.message
            : err instanceof Error
              ? err.message
              : 'Failed to load summary'
          setSummaryError(msg)
        }
      })
      .finally(() => {
        if (!cancelled) setSummaryLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    let cancelled = false
    setScoresLoading(true)
    setScoresError(null)
    axios
      .get<ScoreItem[]>(`${API_BASE}/api/scores`, {
        params: { verdict: activeTab },
      })
      .then((res) => {
        if (!cancelled) setScores(res.data)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const msg = axios.isAxiosError(err)
            ? (err.response?.data as { detail?: string } | undefined)?.detail ??
              err.message
            : err instanceof Error
              ? err.message
              : 'Failed to load scores'
          setScoresError(msg)
        }
      })
      .finally(() => {
        if (!cancelled) setScoresLoading(false)
      })
    return () => { cancelled = true }
  }, [activeTab])

  const tabs: VerdictTab[] = ['BUY', 'WATCHLIST', 'AVOID']

  return (
    <div className="min-h-screen bg-[#0f172a] text-slate-200 flex flex-col">
      <nav className="border-b border-slate-700/80 bg-slate-900/50 px-4 py-4 sm:px-6">
        <div className="mx-auto flex max-w-[1400px] flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">

          <div className="flex flex-col gap-0.5">
            <h1 className="text-left text-xl font-semibold tracking-tight text-white">
              Stock Advisor
            </h1>
            <p className="text-xs text-slate-500">
              made with 🧡 by{' '}
              <span className="text-[#FF6E00]">Syro</span>
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2 lg:justify-end">
            {summaryLoading ? (
              <Spinner />
            ) : summaryError ? (
              <span className="text-sm text-rose-400">{summaryError}</span>
            ) : summary ? (
              <>
                <span className="rounded-full bg-slate-700/80 px-3 py-1 text-sm text-slate-200">
                  Total{' '}
                  <span className="font-semibold text-white">
                    {summary.total_scored}
                  </span>
                </span>
                <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-sm text-emerald-400 ring-1 ring-emerald-500/30">
                  BUY{' '}
                  <span className="font-semibold">{summary.buy_count}</span>
                </span>
                <span className="rounded-full bg-amber-500/15 px-3 py-1 text-sm text-amber-400 ring-1 ring-amber-500/30">
                  WATCHLIST{' '}
                  <span className="font-semibold">{summary.watchlist_count}</span>
                </span>
                <span className="rounded-full bg-rose-500/15 px-3 py-1 text-sm text-rose-400 ring-1 ring-rose-500/30">
                  AVOID{' '}
                  <span className="font-semibold">{summary.avoid_count}</span>
                </span>
              </>
            ) : null}
          </div>
        </div>
      </nav>

      <div className="mx-auto w-full max-w-[1400px] px-4 py-6 sm:px-6 flex-1">
        <div className="mb-6 flex gap-1 rounded-lg bg-slate-800/80 p-1 ring-1 ring-slate-700/80">
          {tabs.map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition sm:flex-none sm:px-6 ${
                activeTab === tab
                  ? 'bg-slate-700 text-white shadow'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {scoresError && (
          <div className="mb-4 rounded-lg border border-rose-500/40 bg-rose-950/40 px-4 py-3 text-sm text-rose-300">
            {scoresError}
          </div>
        )}

        <div className="overflow-hidden rounded-xl border border-slate-700/80 bg-slate-900/40">
          {scoresLoading ? (
            <div className="flex min-h-[240px] flex-col items-center justify-center gap-3 py-16">
            <Spinner />
            <p className="text-xs text-slate-500 animate-pulse">Loading stocks — may take a moment on first load...</p>
          </div>
          ) : scores.length === 0 ? (
            <div className="flex min-h-[240px] flex-col items-center justify-center gap-2 py-16 text-slate-500">
              <p className="text-lg font-medium text-slate-400">No stocks</p>
              <p className="text-sm">Nothing matched this tab.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1100px] border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-700 bg-slate-900/80 text-xs uppercase tracking-wide text-slate-400">
                    <th className="whitespace-nowrap px-3 py-3 font-medium">Ticker</th>
                    <th className="whitespace-nowrap px-3 py-3 font-medium">Sector</th>
                    <th className="whitespace-nowrap px-3 py-3 font-medium">Score</th>
                    <th className="whitespace-nowrap px-3 py-3 font-medium">Quality</th>
                    <th className="whitespace-nowrap px-3 py-3 font-medium">Valuation</th>
                    <th className="whitespace-nowrap px-3 py-3 font-medium">Technical</th>
                    <th className="whitespace-nowrap px-3 py-3 font-medium">Entry (₹)</th>
                    <th className="whitespace-nowrap px-3 py-3 font-medium">Target (₹)</th>
                    <th className="whitespace-nowrap px-3 py-3 font-medium">Stop Loss (₹)</th>
                    <th className="whitespace-nowrap px-3 py-3 font-medium">R/R</th>
                    <th className="whitespace-nowrap px-3 py-3 font-medium">RSI</th>
                    <th className="whitespace-nowrap px-3 py-3 font-medium">vs 50DMA</th>
                    <th className="whitespace-nowrap px-3 py-3 font-medium">vs 200DMA</th>
                    <th className="whitespace-nowrap px-3 py-3 font-medium">ROE%</th>
                    <th className="whitespace-nowrap px-3 py-3 font-medium">Rev Growth%</th>
                    <th className="whitespace-nowrap px-3 py-3 font-medium">Promoter%</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/60">
                  {scores.map((row) => (
                    <tr key={row.ticker} className="hover:bg-slate-800/50">
                      <td className="whitespace-nowrap px-3 py-2.5 font-bold text-white">{row.ticker}</td>
                      <td className="max-w-[140px] truncate px-3 py-2.5 text-slate-300">{row.sector ?? '—'}</td>
                      <td className="whitespace-nowrap px-3 py-2.5">
                        <span className={`inline-flex min-w-[3rem] justify-center rounded-md px-2 py-0.5 text-xs font-semibold ${scoreBadgeClass(row.final_score)}`}>
                          {fmt(row.final_score)}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-3 py-2.5 tabular-nums text-slate-300">{fmt(row.business_quality_score)}</td>
                      <td className="whitespace-nowrap px-3 py-2.5 tabular-nums text-slate-300">{fmt(row.valuation_score)}</td>
                      <td className="whitespace-nowrap px-3 py-2.5 tabular-nums text-slate-300">{fmt(row.technical_score)}</td>
                      <td className="whitespace-nowrap px-3 py-2.5 tabular-nums text-slate-300">{fmt(row.entry_price)}</td>
                      <td className="whitespace-nowrap px-3 py-2.5 tabular-nums text-emerald-400">{fmt(row.target_price)}</td>
                      <td className="whitespace-nowrap px-3 py-2.5 tabular-nums text-slate-300">{fmt(row.stop_loss)}</td>
                      <td className="whitespace-nowrap px-3 py-2.5 tabular-nums text-slate-300">{fmt(row.risk_reward)}</td>
                      <td className={`whitespace-nowrap px-3 py-2.5 tabular-nums ${rsiTextClass(row.rsi)}`}>{fmt(row.rsi)}</td>
                      <td className={`whitespace-nowrap px-3 py-2.5 tabular-nums ${dmaTextClass(row.price_vs_50dma)}`}>{fmt(row.price_vs_50dma)}</td>
                      <td className={`whitespace-nowrap px-3 py-2.5 tabular-nums ${dmaTextClass(row.price_vs_200dma)}`}>{fmt(row.price_vs_200dma)}</td>
                      <td className="whitespace-nowrap px-3 py-2.5 tabular-nums text-slate-300">{fmt(row.roe)}</td>
                      <td className="whitespace-nowrap px-3 py-2.5 tabular-nums text-slate-300">{fmt(row.revenue_growth_3yr)}</td>
                      <td className="whitespace-nowrap px-3 py-2.5 tabular-nums text-slate-300">{fmt(row.promoter_holding)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <footer className="border-t border-slate-700/80 bg-slate-900/50 py-4 px-4 sm:px-6 mt-6">
        <div className="mx-auto max-w-[1400px] flex items-center justify-between">
          <div className="flex items-center gap-4">
            <span className="text-xs text-slate-500">Check out:</span>
            <a href="https://www.instagram.com/syro.ig/" target="_blank" rel="noopener noreferrer" className="text-xs text-slate-300 underline underline-offset-2 hover:text-white transition-colors font-medium">
              Instagram
            </a>
            <a href="https://www.linkedin.com/in/soumojitg" target="_blank" rel="noopener noreferrer" className="text-xs text-slate-300 underline underline-offset-2 hover:text-white transition-colors font-medium">
              LinkedIn
            </a>
          </div>
          <a href="https://docs.google.com/document/d/1Q_yVIUlCQjCcxXt-6Rj_oQOKghdG44gqPYHC2Qk8KI4/edit?usp=sharing" target="_blank" rel="noopener noreferrer" className="text-xs text-slate-300 underline underline-offset-2 hover:text-white transition-colors font-medium">
            How to Use
          </a>
        </div>
      </footer>
    </div>
  )
}