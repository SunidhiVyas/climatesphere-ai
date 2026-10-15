import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import Globe from '../components/Globe'
import { PlaceSearch } from '../components/RegionPicker'
import { ErrorBox, fmt, Kpi, Loading, signed } from '../components/ui'
import { useAsync, useSelection } from '../state'

const LAYERS = [['temp', 'Temperature', '#FF7038'], ['rain', 'Precipitation', '#00E5FF'], ['wind', 'Wind', '#24F0D0'], ['cloud', 'Cloud cover', '#F5F9FF'], ['dry', 'Dryness', '#FFC857']]

export default function Explore() {
  const nav = useNavigate()
  const { sel, setSel } = useSelection()
  const [layer, setLayer] = useState('temp')
  const [picked, setPicked] = useState(null)
  const presets = useAsync(() => api.presets(), [])
  const lay = useAsync((s) => api.layer(layer, s), [layer])
  const overlay = useMemo(() => (lay.data ? { name: lay.data.name, values: lay.data.values, width: lay.data.width, height: lay.data.height } : null), [lay.data])

  const region = picked && { name: picked.name, lat: picked.lat, lon: picked.lon }
  const summary = useAsync((s) => api.summary({ region, from: sel.from, to: sel.to }, s), [picked?.lat, picked?.lon, sel.from, sel.to], !!picked)
  const air = useAsync((s) => api.aerosol(region, s), [picked?.lat, picked?.lon], !!picked)

  const pickPoint = (p) => setPicked({ name: p.name || `${p.lat.toFixed(1)}°, ${p.lon.toFixed(1)}°`, lat: Math.round(p.lat * 10) / 10, lon: Math.round(p.lon * 10) / 10 })
  const open = () => { setSel(s => ({ ...s, region })); nav('/dashboard') }

  return (
    <div className="wrap">
      <span className="pill">GLOBAL CLIMATE INTELLIGENCE</span>
      <h1 className="t">Explore climate hazards <span className="g">across the planet</span></h1>
      <p className="lead" style={{ marginBottom: 22 }}>Rotate the globe, switch to a live data layer, and click anywhere (or a hotspot) to see that region's hazard history and air quality.</p>

      <div className="split" style={{ gridTemplateColumns: 'minmax(0,1.25fr) minmax(340px,1fr)' }}>
        <div className="glass">
          <div className="layers" role="group" aria-label="Data layer">
            {LAYERS.map(([k, l, c]) => <button key={k} className="chip" aria-pressed={layer === k} onClick={() => setLayer(k)} style={{ borderColor: c }}>{l}</button>)}
            {lay.loading && <span className="spin" aria-label="Loading layer" />}
          </div>
          <Globe hotspots={presets.data?.presets || []} selected={picked} overlay={overlay} onHotspot={pickPoint} onPick={pickPoint} autoRotate={!picked} />
          {lay.error && <p className="hint" role="alert" style={{ color: '#ffb4ae' }}>Layer unavailable: {lay.error.message}. The globe shows geography only; no values are invented.</p>}
          {lay.data && <p className="hint">{lay.data.label} · {lay.data.min} to {lay.data.max} {lay.data.unit} · {lay.data.source} · observed {new Date(lay.data.observed_at).toLocaleString()} · 10° grid, smoothed for display.</p>}
        </div>

        <div className="grid" style={{ minWidth: 0 }}>
          <div className="glass"><h3>SELECT A REGION</h3><PlaceSearch onPick={pickPoint} />
            <p className="hint">Analysis period: {sel.from}–{sel.to} (change it on the Dashboard).</p></div>

          {!picked && <div className="glass state">Click a glowing hotspot or anywhere on the globe.</div>}
          {picked && (
            <>
              <div className="glass">
                <h3>{picked.name.toUpperCase()} <button className="btn pri xs" onClick={open}>Full analysis →</button></h3>
                <p className="muted">{picked.lat}°, {picked.lon}°</p>
              </div>
              {summary.loading && <div className="glass"><Loading>Computing hazard trends for {picked.name}… (first request for a region can take 10–40 s)</Loading></div>}
              {summary.error && <ErrorBox error={summary.error} />}
              {summary.data && (
                <div className="grid g3">
                  {[['heatwaves', 'Heatwave events', '#FF7038'], ['extreme_rainfall', 'Heavy-rain days', '#00E5FF'], ['drought', 'Dry spells', '#FFC857']].map(([k, l, c]) => {
                    const m = summary.data[k]
                    return <Kpi key={k} label={l.toUpperCase()} value={m.value} color={c}
                      sub={`${m.change_pct === null ? 'change n/a' : signed(m.change_pct, 0, '%') + ' vs first decade'} · ${m.significant ? 'significant' : 'not significant'}`} />
                  })}
                </div>
              )}
              {summary.data && <p className="hint">Cyclones: not shown - tropical-cyclone tracks cannot be derived from daily weather data.</p>}
              {air.loading && <div className="glass"><Loading>Loading air quality…</Loading></div>}
              {air.error && <p className="hint" style={{ color: '#ffb4ae' }}>Air quality unavailable: {air.error.message}</p>}
              {air.data && (
                <div className="glass">
                  <h3>AIR QUALITY NOW <span className="badge live">LIVE</span></h3>
                  <div className="grid g4" style={{ gap: 10 }}>
                    {[['PM2.5', air.data.pm], ['PM10', air.data.pm10], ['Dust', air.data.dust], ['AOD', air.data.aod]].map(([n, v]) => (
                      <div key={n}><small className="muted">{n}</small><div style={{ fontSize: 22, fontWeight: 700 }}>{fmt(v.value)}</div><small className="muted">{v.unit}</small></div>
                    ))}
                  </div>
                  <p className="hint">WHO 24-hour PM2.5 guideline: {air.data.who_guideline_pm25_24h} µg/m³. {air.data.source}.</p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
