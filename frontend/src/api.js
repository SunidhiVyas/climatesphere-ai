// Thin client for the FastAPI backend. In dev, Vite proxies /api -> :8000. In production set VITE_API_BASE.
const BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status }
}

export function qs(obj) {
  const p = new URLSearchParams()
  Object.entries(obj).forEach(([k, v]) => { if (v !== null && v !== undefined && v !== '') p.set(k, v) })
  return p.toString()
}

async function get(path, params = {}, signal) {
  let res
  try { res = await fetch(`${BASE}${path}?${qs(params)}`, { signal }) }
  catch (e) { if (e.name === 'AbortError') throw e; throw new ApiError('Cannot reach the API server. Is the backend running?', 0) }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`
    try { const j = await res.json(); msg = typeof j.detail === 'string' ? j.detail : j.error || (Array.isArray(j.detail) ? j.detail.map(d => d.msg).join('; ') : msg) } catch { /* ignore */ }
    throw new ApiError(msg, res.status)
  }
  return res.json()
}

async function post(path, body) {
  let res
  try { res = await fetch(`${BASE}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }) }
  catch { throw new ApiError('Cannot reach the API server.', 0) }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`
    try { const j = await res.json(); msg = j.error || (Array.isArray(j.detail) ? j.detail.map(d => d.msg).join('; ') : j.detail) || msg } catch { /* ignore */ }
    throw new ApiError(msg, res.status)
  }
  return res.json()
}

/** region object -> query params understood by the backend */
export function regionParams(r) {
  if (r.bbox) return { south: r.bbox.south, west: r.bbox.west, north: r.bbox.north, east: r.bbox.east, name: r.name }
  return { lat: r.lat, lon: r.lon, name: r.name }
}

export function analysisParams(s) {
  return { ...regionParams(s.region), hazard: s.hazard, from: s.from, to: s.to, percentile: s.percentile, min_days: s.minDays, mode: s.mode }
}

export const api = {
  health: (signal) => get('/api/health', {}, signal),
  presets: () => get('/api/presets'),
  region: (q, signal) => get('/api/region', { q }, signal),
  trends: (s, signal) => get('/api/trends', analysisParams(s), signal),
  summary: (s, signal) => get('/api/summary', { ...regionParams(s.region), from: s.from, to: s.to }, signal),
  layer: (name, signal) => get('/api/layer', { name }, signal),
  aerosol: (r, signal) => get('/api/aerosol', regionParams(r), signal),
  projections: (r, year, signal) => get('/api/projections', { ...regionParams(r), year }, signal),
  insights: (r, year, signal) => get('/api/insights', { ...regionParams(r), year }, signal),
  impact: (signal) => get('/api/impact', {}, signal),
  newsletter: (email) => post('/api/newsletter', { email }),
  join: (name, email) => post('/api/community/join', { name, email }),
  exportUrl: (kind, s, extra = {}) => {
    const path = { csv: '/api/export/csv', pdf: '/api/export/pdf', png: '/api/plot.png' }[kind]
    return `${BASE}${path}?${qs({ ...analysisParams(s), ...extra })}`
  },
}
