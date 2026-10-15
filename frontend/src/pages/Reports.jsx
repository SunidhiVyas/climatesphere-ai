import { useState } from 'react'
import { api } from '../api'
import { ErrorBox, fmt, HAZARDS, Loading, signed } from '../components/ui'
import { PlaceSearch } from '../components/RegionPicker'
import { useAsync, useSelection } from '../state'

const SOURCES = [
  ['Open-Meteo Historical Weather API', 'ERA5 / ERA5-Land reanalysis (Copernicus / ECMWF), daily Tmax, Tmin, precipitation, 1950–present.', 'https://open-meteo.com/en/docs/historical-weather-api'],
  ['Open-Meteo Climate API', 'CMIP6 HighResMIP projections to 2050 (SSP5-8.5).', 'https://open-meteo.com/en/docs/climate-api'],
  ['Open-Meteo Air Quality API', 'CAMS global atmospheric composition forecasts (PM2.5, PM10, dust, AOD).', 'https://open-meteo.com/en/docs/air-quality-api'],
  ['World Bank WDI', 'Global renewable-energy share, forest area and CO₂ per person.', 'https://data.worldbank.org'],
]

export default function Reports() {
  const { sel, patch } = useSelection()
  const [preview, setPreview] = useState(false)
  const impact = useAsync((s) => api.impact(s), [])
  const [f, setF] = useState({ name: '', email: '' })
  const [msg, setMsg] = useState(null)
  const valid = Number.isInteger(+sel.from) && Number.isInteger(+sel.to) && sel.to - sel.from >= 4
  const s = { ...sel, from: +sel.from, to: +sel.to }

  async function join(e) {
    e.preventDefault(); setMsg(null)
    try { await api.join(f.name, f.email); setMsg({ ok: true, t: 'Welcome to the community!' }); setF({ name: '', email: '' }) } catch (ex) { setMsg({ ok: false, t: ex.message }) }
  }

  return (
    <div className="wrap">
      <span className="pill">REPORTS</span>
      <h1 className="t">Export your analysis, <span className="g">cite the sources</span></h1>
      <p className="lead" style={{ marginBottom: 24 }}>Build a CSV or PDF report for any region and hazard. Reports include the method, statistics, caveats and data-quality notes.</p>

      <div className="grid g2">
        <div className="glass">
          <h3>REPORT BUILDER</h3>
          <label className="f">REGION</label><PlaceSearch onPick={r => patch({ region: r })} />
          <p className="muted" style={{ marginTop: 8 }}>Selected: <b style={{ color: 'var(--tx)' }}>{sel.region.name}</b></p>
          <label className="f" htmlFor="rh">HAZARD</label>
          <select id="rh" className="in" value={sel.hazard} onChange={e => patch({ hazard: e.target.value, minDays: '' })}>{HAZARDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          <div className="row" style={{ marginTop: 12, flexWrap: 'nowrap' }}>
            <input className="in" type="number" aria-label="From year" value={sel.from} onChange={e => patch({ from: e.target.value })} />
            <span className="muted">to</span>
            <input className="in" type="number" aria-label="To year" value={sel.to} onChange={e => patch({ to: e.target.value })} />
          </div>
          {!valid && <p className="hint" role="alert" style={{ color: '#ffb4ae' }}>Choose a range of at least 5 years.</p>}
          <div className="row" style={{ marginTop: 16 }}>
            <button className="btn pri sm" disabled={!valid} onClick={() => setPreview(true)}>Preview plot</button>
            {valid && <>
              <a className="btn sm" href={api.exportUrl('csv', s)}>⬇ CSV</a>
              <a className="btn sm" href={api.exportUrl('csv', s, { kind: 'events' })}>⬇ Events CSV</a>
              <a className="btn sm" href={api.exportUrl('pdf', s)}>⬇ PDF</a>
            </>}
          </div>
          <p className="hint">The first export for a new region fetches data from the provider and can take up to ~40 s.</p>
        </div>
        <div className="glass" style={{ display: 'grid', placeItems: 'center', minHeight: 260 }}>
          {preview && valid
            ? <img key={JSON.stringify(s)} src={api.exportUrl('png', s)} alt={`Trend plot for ${sel.region.name}`} style={{ maxWidth: '100%', borderRadius: 8, background: '#fff' }} />
            : <p className="muted">Click "Preview plot" to render the server-generated trend chart.</p>}
        </div>
      </div>

      <h2 className="t" style={{ marginTop: 44 }}>Global progress indicators</h2>
      <p className="muted" style={{ marginBottom: 14 }}>World aggregates from the World Bank. Context for climate action - not a forecast.</p>
      {impact.loading && <div className="glass"><Loading>Loading World Bank indicators…</Loading></div>}
      {impact.error && <ErrorBox error={impact.error} />}
      {impact.data && (
        <div className="grid g3">
          {impact.data.indicators.map(i => (
            <div className="glass kpi" key={i.key} style={{ '--c': '#24F0D0' }} title={i.definition}>
              <small>{i.label.toUpperCase()}</small><b>{fmt(i.value, 1)}</b>
              <span>{i.unit} · {i.year}{i.reference ? ` · ${signed(i.change_pct, 0, '%')} vs ${i.reference.year}` : ''}</span>
              <p className="hint">{i.definition}</p>
            </div>
          ))}
        </div>
      )}

      <div className="grid g2" style={{ marginTop: 44 }}>
        <div className="glass" id="data-sources">
          <h3>DATA SOURCES</h3>
          <ul style={{ listStyle: 'none', padding: 0 }}>{SOURCES.map(([n, d, u]) => <li key={n} style={{ marginBottom: 12 }}><a href={u} target="_blank" rel="noreferrer" style={{ color: 'var(--cy)' }}>{n}</a><p className="muted">{d}</p></li>)}</ul>
        </div>
        <form className="glass" onSubmit={join}>
          <h3>JOIN THE COMMUNITY</h3>
          <label className="f" htmlFor="jn">NAME</label><input id="jn" className="in" required minLength={2} maxLength={80} value={f.name} onChange={e => setF({ ...f, name: e.target.value })} />
          <label className="f" htmlFor="je">EMAIL</label><input id="je" className="in" type="email" required maxLength={254} value={f.email} onChange={e => setF({ ...f, email: e.target.value })} />
          <button className="btn pri sm" type="submit" style={{ marginTop: 16 }}>Join</button>
          {msg && <p className="hint" role="status" style={{ color: msg.ok ? 'var(--tq)' : '#ffb4ae' }}>{msg.t}</p>}
        </form>
      </div>
    </div>
  )
}
