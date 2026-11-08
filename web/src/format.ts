// One place for number formatting. Every *_pct field from the API is a fraction (0.05 is 5%).
// null/undefined render as an em dash, never as 0.

const DASH = '—'

const moneyFmt = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const pctFmt = new Intl.NumberFormat('en-US', {
  style: 'percent',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  signDisplay: 'exceptZero',
})

// Axis labels: as few digits as the value needs, so bin edges read -2%, 0%, +0.5%.
const pctShortFmt = new Intl.NumberFormat('en-US', {
  style: 'percent',
  maximumFractionDigits: 2,
  signDisplay: 'exceptZero',
})

// Unsigned shares (a win rate, a volatility): +51% would read as a change.
const shareFmt = new Intl.NumberFormat('en-US', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 })

const ratioFmt = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const numFmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 4 })

export function money(v: number | null | undefined): string {
  return v == null ? DASH : moneyFmt.format(v)
}

export function pct(v: number | null | undefined): string {
  return v == null ? DASH : pctFmt.format(v)
}

export function pctShort(v: number | null | undefined): string {
  return v == null ? DASH : pctShortFmt.format(v)
}

export function share(v: number | null | undefined): string {
  return v == null ? DASH : shareFmt.format(v)
}

/** Two decimals, for Sharpe, beta and the like. */
export function ratio(v: number | null | undefined): string {
  return v == null ? DASH : ratioFmt.format(v)
}

/** A count of calendar days: '128 d'. */
export function days(v: number | null | undefined): string {
  return v == null ? DASH : `${v} d`
}

/** 'SPY' from 'SPY.US': the exchange suffix is noise in labels. */
export function ticker(symbol: string): string {
  return symbol.replace(/\.US$/, '')
}

export function num(v: number | null | undefined): string {
  return v == null ? DASH : numFmt.format(v)
}

/** 'pos' / 'neg' for green / red; '' for zero or missing. */
export function pnlClass(v: number | null | undefined): '' | 'pos' | 'neg' {
  if (v == null || v === 0) return ''
  return v > 0 ? 'pos' : 'neg'
}

/** 'YYYY-MM-DD' from an ISO date or datetime string, as the API sends them. */
export function day(v: string | null | undefined): string {
  return v == null ? DASH : v.slice(0, 10)
}

/** The middle value, or null for an empty list. */
export function median(values: number[]): number | null {
  if (values.length === 0) return null
  const s = [...values].sort((a, b) => a - b)
  const mid = Math.floor(s.length / 2)
  return s.length % 2 ? s[mid]! : (s[mid - 1]! + s[mid]!) / 2
}
