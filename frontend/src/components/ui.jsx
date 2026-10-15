export function Loading({ children = 'Loading…' }) {
  return <div className="state" role="status"><span className="spin" />{children}</div>
}
export function ErrorBox({ error, retry }) {
  return (
    <div className="glass err" role="alert">
      <b>Something went wrong.</b>
      <p style={{ margin: '6px 0 0' }}>{error?.message || String(error)}</p>
      {retry && <button className="btn xs" style={{ marginTop: 12 }} onClick={retry}>Try again</button>}
    </div>
  )
}
export function Kpi({ label, value, sub, color = 'var(--cy)' }) {
  return (
    <div className="glass kpi" style={{ '--c': color }}>
      <small>{label}</small><b>{value ?? '—'}</b><span>{sub}</span>
    </div>
  )
}
export const fmt = (v, d = 1) => (v === null || v === undefined || Number.isNaN(v) ? '—' : Number(v).toFixed(d))
export const signed = (v, d = 1, suffix = '') => (v === null || v === undefined ? '—' : `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(d)}${suffix}`)
export const HAZARDS = [['heatwave', 'Heatwave'], ['rainfall', 'Heavy rainfall'], ['drought', 'Dry spells (drought proxy)']]
export const HAZARD_COLOR = { heatwave: '#FF7038', rainfall: '#00E5FF', drought: '#FFC857' }
