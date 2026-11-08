import type { components } from './schema'

export type Portfolio = components['schemas']['Portfolio']
export type Transaction = components['schemas']['Transaction']
export type ChartData = components['schemas']['ChartData']
export type SymbolRow = components['schemas']['Symbol']
export type SignalRow = components['schemas']['SignalRow']

/** A non-2xx response; `message` carries FastAPI's `detail` when the body has one. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// FastAPI's `detail` is a string for HTTPException and a list of {loc, msg} for 422 validation errors.
function describe(detail: unknown): string | null {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const msgs = detail.map((d: { loc?: unknown[]; msg?: string }) =>
      [d.loc?.slice(1).join('.'), d.msg].filter(Boolean).join(': '),
    )
    return msgs.join('; ') || null
  }
  return null
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`)
  if (!res.ok) {
    let detail: string | null = null
    try {
      detail = describe(((await res.json()) as { detail?: unknown }).detail)
    } catch {
      // not JSON (a proxy error page, say): fall back to the status line
    }
    throw new ApiError(res.status, detail ?? `${res.status} ${res.statusText} — ${path}`)
  }
  return res.json() as Promise<T>
}

// ~5,600 rows that change at most nightly: fetch once per page load, shared by every mount.
// A failed request is dropped from the cache so the next caller retries.
let symbolsOnce: Promise<SymbolRow[]> | null = null

export const api = {
  portfolio: () => get<Portfolio>('/portfolio'),
  transactions: () => get<Transaction[]>('/transactions'),
  symbols: () =>
    (symbolsOnce ??= get<SymbolRow[]>('/symbols').catch((e: unknown) => {
      symbolsOnce = null
      throw e
    })),
  chart: (symbol: string, adjusted = false) =>
    get<ChartData>(`/chart/${encodeURIComponent(symbol)}?adjusted=${adjusted}`),
  signals: (days = 90, minRanking = 44) =>
    get<SignalRow[]>(`/signals?days=${days}&min_ranking=${minRanking}`),
}
