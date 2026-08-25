/**
 * `VITE_API_BASE_URL` picks the AEGIS API origin explicitly (e.g. for a
 * deployed backend). Left unset, requests go to a relative `/api/...` path,
 * which `vite.config.ts`'s dev proxy forwards to `http://localhost:8000` --
 * so `npm run dev` works against a local `uvicorn aegis.api.app:app` with no
 * CORS configuration needed on either side.
 */
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "";
