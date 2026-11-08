import type { Router } from 'vue-router'

// After a deploy, a tab opened on the previous release still runs the old bundle, and its lazy
// route chunks are gone from the server (which answers them with a real 404). Reload once to
// pick up the new index.html; this is the recovery Vite's docs recommend for deployments.

const KEY = 'turtle-web:stale-chunk-reload'
const WINDOW_MS = 10_000 // never reload twice within this window: a genuinely broken build must not loop

// The message each engine gives for a failed dynamic import, plus Vite's for a failed CSS preload.
const CHUNK_ERROR =
  /dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unable to preload CSS/i

function reloadOnce(path: string): void {
  try {
    const last = Number(sessionStorage.getItem(KEY))
    if (Date.now() - last < WINDOW_MS) return
    sessionStorage.setItem(KEY, String(Date.now()))
  } catch {
    // sessionStorage unavailable (private mode, say): reload anyway, the window just can't hold
  }
  window.location.assign(path)
}

export function reloadOnStaleChunks(router: Router): void {
  // Every lazy import in this app is a route component, so the router sees each failure, with
  // the destination. Vite's own 'vite:preloadError' event is deliberately not handled: reloading
  // there reloads the *current* URL before the router can navigate, dropping the user's click.
  router.onError((error: unknown, to) => {
    if (error instanceof Error && CHUNK_ERROR.test(error.message)) reloadOnce(to.fullPath)
  })
}
