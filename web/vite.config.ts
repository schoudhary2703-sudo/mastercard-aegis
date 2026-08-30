import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

/**
 * Where `npm run dev` sends `/api/*`.
 *
 * Resolution order, first hit wins:
 *   1. AEGIS_API_PROXY_TARGET in the shell environment
 *   2. AEGIS_API_PROXY_TARGET in web/.env.local (or .env)
 *   3. http://127.0.0.1:8000 -- a local `uvicorn aegis.api.app:app`
 *
 * The local default is 127.0.0.1, not localhost: on Windows, Node resolves
 * `localhost` to the IPv6 ::1 first, while uvicorn binds IPv4 only by
 * default, so the proxy fails with `ECONNREFUSED ::1:8000` even though the
 * API is running. The literal IPv4 address sidesteps the ambiguity.
 *
 * The .env route exists because a shell variable is easy to lose: set it in
 * one terminal, run the dev server in another, and every panel silently
 * renders "Could not reach the AEGIS API". A file survives a reopened
 * terminal and is checked here rather than guessed at.
 *
 * Reviewing the UI therefore needs no Python at all -- point it at the
 * deployed backend with one line in web/.env.local:
 *
 *   AEGIS_API_PROXY_TARGET=https://mastercard-aegis.onrender.com
 *
 * Deliberately the dev proxy rather than VITE_API_BASE_URL: the proxy is
 * server-side, so the browser stays same-origin on localhost:5173 and the
 * deployed API needs no extra AEGIS_API_CORS_ORIGINS entry. Pointing the
 * browser straight at a remote origin would be blocked by CORS.
 */
// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Third arg "" disables Vite's VITE_ prefix filter: this value is consumed
  // here in the Node config, never inlined into client code.
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget =
    process.env.AEGIS_API_PROXY_TARGET ?? env.AEGIS_API_PROXY_TARGET ?? 'http://127.0.0.1:8000'

  // Printed on every dev boot so a failing panel is diagnosable from the
  // terminal instead of the browser console.
  if (mode === 'development') {
    console.log(`\n  AEGIS API proxy → ${apiTarget}\n`)
  }

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
  }
})
