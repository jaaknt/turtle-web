import { execSync } from 'node:child_process'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// The version in the nav bar, and whether this build *is* a release.
//
// A release is decided by who built it, not by what the version string looks like: release.yml
// sets APP_VERSION to the tag, and only then is there a release page to link to (built from the
// repo Actions names in GITHUB_SERVER_URL / GITHUB_REPOSITORY, so the slug is not hardcoded).
// Any other build shows `git describe --tags --always --dirty`, unlinked, even on a clean
// checkout of a tag: v0.3.1-2-gabc1234-dirty locally, or a bare short SHA in CI's shallow,
// tagless checkout. Read once at config load, so a running dev server keeps the value it started
// with until it is restarted.
function release(): { version: string; url: string } | null {
  const { APP_VERSION, GITHUB_SERVER_URL, GITHUB_REPOSITORY } = process.env
  if (!APP_VERSION) return null
  const url = GITHUB_SERVER_URL && GITHUB_REPOSITORY ? `${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/releases/tag/${APP_VERSION}` : ''
  return { version: APP_VERSION, url }
}

function describe(): string {
  try {
    return execSync('git describe --tags --always --dirty', { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim()
  } catch {
    return 'dev' // no git, e.g. a source tarball
  }
}

const rel = release()

// The dev proxy is why the API needs no CORS middleware: the browser only ever sees one origin.
export default defineConfig({
  plugins: [vue()],
  define: {
    __APP_VERSION__: JSON.stringify(rel?.version ?? describe()),
    __APP_RELEASE_URL__: JSON.stringify(rel?.url ?? ''), // '' = not a release build, no link
  },
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
