import { useState } from 'react'
import { api } from '../api'
import { PlaceSearch } from '../components/RegionPicker'
import { ErrorBox, Kpi, Loading } from '../components/ui'
import { useAsync, useSelection } from '../state'

const YEARS = [2030, 2040, 2050]
const META = { temp: ['WARMING', '#FF3D32'], heat: ['EXTRA HOT DAYS / YEAR', '#FF7038'], rain: ['ANNUAL RAINFALL CHANGE', '#00E5FF'], drought: ['EXTRA DRY DAYS / YEAR', '#FFC857'] }

export default function AILab() {
  const { sel, patch } = useSelection()
  const [year, setYear] = useState(2050)
  const [nonce, setNonce] = useState(0)
  const proj = useAsync((s) => api.projections(sel.region, year, s), [sel.region.lat, sel.region.lon, year])
  const ins = useAsync((s) => api.insights(sel.region, year, s), [sel.region.lat, sel.region.lon, year, nonce])

  return (
    <div className="wrap">
      <span className="pill">AI LAB</span>
      <h1 className="t">Visualize tomorrow. <span className="g">Act today.</span></h1>
      <p className="lead" style={{ marginBottom: 24 }}>Climate-model projections (CMIP6) for any place, with a plain-language explanation that is generated only from the numbers shown.</p>

      <div className="glass" style={{ marginBottom: 18 }}>
        <div className="grid g2" style={{ alignItems: 'end' }}>
          <div><label className="f">REGION</label><PlaceSearch onPick={r => patch({ region: r })} />
            <p className="muted" style={{ marginTop: 8 }}>Selected: <b style={{ color: 'var(--tx)' }}>{sel.region.name}</b></p></div>
          <div><label className="f">PROJECTION YEAR (decade centred on…)</label>
            <div className="seg" role="group" aria-label="Year">{YEARS.map(y => <button key={y} aria-pressed={year === y} onClick={() => setYear(y)}>{y}</button>)}</div></div>
        </div>
      </div>

      <div className="grid">
        {proj.loading && <div className="glass"><Loading>Loading CMIP6 climate-model data…</Loading></div>}
        {proj.error && <ErrorBox error={proj.error} />}
        {proj.data && (
          <>
            <div className="grid g4">
              {Object.entries(proj.data.metrics).map(([k, m]) => (
                <Kpi key={k} label={META[k][0]} value={m.display} color={META[k][1]}
                  sub={`model range ${m.range[0]} to ${m.range[1]} · vs ${m.baseline}`} />
              ))}
            </div>
            <p className="hint">Window {proj.data.window} · models: {proj.data.models.join(', ')} · {proj.data.metrics.temp.source} · pathway {proj.data.metrics.temp.pathway}</p>
            <div className="glass" style={{ borderColor: 'rgba(255,200,87,.4)' }}>
              <span className="badge warn">LIMITS OF THIS SOURCE</span>
              <p className="muted" style={{ marginTop: 8 }}>{proj.data.note} "Extra hot days" counts days above the location's own 1991–2020 95th-percentile Tmax in each model.</p>
            </div>
          </>
        )}

        <div className="glass">
          <h3>AI INSIGHTS
            <span className="row">{ins.data && <span className={`badge ${ins.data.generated ? 'live' : 'mute'}`}>{ins.data.generated ? 'LLM' : 'RULE-BASED'}</span>}
              <button className="btn xs" onClick={() => setNonce(n => n + 1)} disabled={ins.loading}>Regenerate</button></span></h3>
          {ins.loading && <Loading>Writing explanation…</Loading>}
          {ins.error && <ErrorBox error={ins.error} />}
          {ins.data && <><p style={{ lineHeight: 1.7, fontSize: 15 }}>{ins.data.text}</p><p className="hint">Model: {ins.data.model} · {ins.data.source}. Always check the numbers above and the caveats on the Dashboard.</p></>}
        </div>
      </div>
    </div>
  )
}
