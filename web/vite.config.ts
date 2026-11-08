import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// The dev proxy is why the API needs no CORS middleware: the browser only ever sees one origin.
export default defineConfig({
  plugins: [vue()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
