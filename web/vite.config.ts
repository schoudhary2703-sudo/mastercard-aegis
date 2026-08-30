import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

/**
 * Where `npm run dev` sends `/api/*`.
 *
 * Defaults to a local `uvicorn aegis.api.app:app --port 8000`. Set
 * `AEGIS_API_PROXY_TARGET` to work on the UI without running the Python API
 * at all -- e.g. against the deployed backend:
 *
 *   AEGIS_API_PROXY_TARGET=https://mastercard-aegis.onrender.com npm run dev
 *
 * This is a *server-side* proxy, so the browser only ever talks to
 * localhost:5173 and no CORS entry is needed for the deployed API. Pointing
 * the browser straight at a remote origin via VITE_API_BASE_URL would need
 * that origin in AEGIS_API_CORS_ORIGINS; this does not.
 */
const apiTarget = process.env.AEGIS_API_PROXY_TARGET ?? "http://localhost:8000"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
})
