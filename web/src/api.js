// Thin client for the Flask match API. The server has open CORS in dev, so we
// call it directly. Override the base with VITE_API_BASE when the server isn't
// at http://localhost:8080.
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8080'

async function req(path, opts = {}) {
  let resp
  try {
    resp = await fetch(API_BASE + path, {
      headers: { 'Content-Type': 'application/json' },
      ...opts,
    })
  } catch (e) {
    throw new Error(`Can't reach the server at ${API_BASE}. Is it running?`)
  }
  let data = {}
  try { data = await resp.json() } catch { /* non-JSON */ }
  if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`)
  return data
}

export const api = {
  base: API_BASE,
  createMatch: (config) =>
    req('/api/matches', { method: 'POST', body: JSON.stringify({ config }) }),
  resolveToken: (token) =>
    req(`/api/resolve-token?token=${encodeURIComponent(token)}`),
  getState: (matchId, token) =>
    req(`/api/matches/${matchId}/state?token=${encodeURIComponent(token)}`),
  submitMove: (matchId, token, move) =>
    req(`/api/matches/${matchId}/moves?token=${encodeURIComponent(token)}`, {
      method: 'POST', body: JSON.stringify({ move }),
    }),
  status: (matchId, token) =>
    req(`/api/matches/${matchId}/status?token=${encodeURIComponent(token)}`),
  advance: (matchId, token) =>
    req(`/api/matches/${matchId}/advance?token=${encodeURIComponent(token)}`, {
      method: 'POST',
    }),
}
