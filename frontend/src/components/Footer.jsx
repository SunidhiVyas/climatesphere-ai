import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAsync } from '../state'

export default function Footer() {
  const [email, setEmail] = useState('')
  const [msg, setMsg] = useState(null)
  const health = useAsync((s) => api.health(s), [])
  async function sub(e) {
    e.preventDefault()
    setMsg(null)
    try { await api.newsletter(email); setMsg({ ok: true, t: 'Thanks - you are subscribed.' }); setEmail('') } catch (ex) { setMsg({ ok: false, t: ex.message }) }
  }
  const up = !!health.data
  return (
    <footer className="ft">
      <div className="ftg">
        <div>
          <div className="brand"><span className="logo" /><span><b>Climate<i>Sphere</i> AI</b></span></div>
          <p className="muted" style={{ marginTop: 12 }}>Historical weather, detected hazards and honest trend statistics for any region.</p>
          <p className="hint"><span className="dot" style={{ background: up ? 'var(--tq)' : health.loading ? 'var(--am)' : 'var(--rd)' }} />
            API {health.loading ? 'checking…' : up ? `online · DB: ${health.data.db.backend}` : 'unreachable'}</p>
        </div>
        <nav aria-label="Product"><h4>PRODUCT</h4><ul><li><Link to="/dashboard">Dashboard</Link></li><li><Link to="/explore">Explore</Link></li><li><Link to="/ai-lab">AI Lab</Link></li></ul></nav>
        <nav aria-label="Resources"><h4>RESOURCES</h4><ul><li><Link to="/reports">Reports</Link></li><li><a href={`${import.meta.env.VITE_API_BASE || ""}/api/docs`} target="_blank" rel="noreferrer">API docs</a></li><li><a href="https://open-meteo.com" target="_blank" rel="noreferrer">Open-Meteo</a></li></ul></nav>
        <div>
          <h4>STAY UPDATED</h4>
          <form onSubmit={sub} className="row" style={{ flexWrap: 'nowrap' }}>
            <label htmlFor="nl" style={{ position: 'absolute', left: -9999 }}>Email address</label>
            <input id="nl" className="in" type="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="Enter your email address…" maxLength={254} />
            <button className="btn sm" type="submit">Subscribe</button>
          </form>
          {msg && <p className="hint" role="status" style={{ color: msg.ok ? 'var(--tq)' : '#ffb4ae' }}>{msg.t}</p>}
        </div>
      </div>
      <div className="fe"><span>© 2026 ClimateSphere AI</span><span>Data: Open-Meteo (ERA5 reanalysis, CMIP6, CAMS) · World Bank</span></div>
    </footer>
  )
}
