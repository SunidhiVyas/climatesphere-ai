import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import Globe from '../components/Globe'
import Reveal from '../components/Reveal'
import { useAsync, useSelection } from '../state'

const FEATURES = [
  ['📈', 'Real Weather Data', 'ERA5 reanalysis from Open-Meteo, cached per region-year in MongoDB.', '/reports'],
  ['🧠', 'AI-Powered Insights', 'Plain-language explanations grounded strictly in computed statistics.', '/ai-lab'],
  ['🌍', 'Interactive Visualizations', 'Globe, map selection and Chart.js time-series for any region.', '/explore'],
  ['🛡', 'Data-Driven Decisions', 'Mann-Kendall and Theil-Sen tests tell you whether a trend is real.', '/trends'],
]
const STEPS = [
  ['Ingest', 'Daily Tmax, Tmin and rainfall are fetched once per region-year and stored in MongoDB.'],
  ['Clean', 'Gaps, impossible values, unit mix-ups and spikes are handled and reported.'],
  ['Detect', 'Percentile rules find heatwaves, heavy-rain days and dry spells.'],
  ['Explain', 'Rolling means, regression and Mann-Kendall give honest, caveated insights.'],
]

export default function Home() {
  const nav = useNavigate()
  const { setSel } = useSelection()
  const presets = useAsync(() => api.presets(), [])
  const health = useAsync((s) => api.health(s), [])
  const [pick, setPick] = useState(null)
  const go = (h) => { setSel(s => ({ ...s, region: { name: h.name, lat: h.lat, lon: h.lon } })); nav('/dashboard') }

  return (
    <>
      <section className="hero">
        <Reveal>
          <span className="pill">REAL DATA &nbsp;•&nbsp; AI POWERED &nbsp;•&nbsp; A SAFER TOMORROW</span>
          <h1 className="t" style={{ fontSize: 'clamp(34px,4.6vw,58px)' }}>Understand the Climate.<br /><span className="g">Anticipate the Change.</span></h1>
          <p className="lead">Analyze historical weather data, detect climate hazards, and explore future trends with the power of AI.</p>
          <div className="cta">
            <Link className="btn pri" to="/dashboard">Explore Dashboard →</Link>
            <Link className="btn" to="/explore">Explore the Data</Link>
          </div>
          <div className="glass" style={{ marginTop: 34, maxWidth: 470 }}>
            <h3>PIPELINE STATUS <span className={`badge ${health.data ? 'live' : health.loading ? 'mute' : 'bad'}`}>{health.data ? 'LIVE' : health.loading ? '…' : 'OFFLINE'}</span></h3>
            {health.data ? (
              <table className="tb"><tbody>
                <tr><td>Database</td><td>{health.data.db.backend}{health.data.db.persistent ? '' : ' (not persistent)'}</td></tr>
                <tr><td>Cached analyses</td><td>{health.data.cache.analyses}</td></tr>
                <tr><td>Cached region-years</td><td>{health.data.cache.weather_years}</td></tr>
                <tr><td>Latest complete year</td><td>{health.data.last_complete_year}</td></tr>
              </tbody></table>
            ) : <p className="muted">{health.loading ? 'Contacting the API…' : 'The API server is not reachable. Start the backend to load real data.'}</p>}
            <p className="hint">Only measured/modelled values returned by the backend are ever shown - nothing is hard-coded.</p>
          </div>
        </Reveal>
        <Reveal delay={160} style={{ position: 'relative' }}>
          <Globe hotspots={presets.data?.presets || []} onHotspot={setPick} selected={pick} autoRotate />
          {pick && (
            <div className="glass" style={{ position: 'absolute', right: 10, bottom: 10, maxWidth: 260 }} role="dialog" aria-label="Region details">
              <b>{pick.name}</b><p className="muted">{pick.country} · {pick.lat.toFixed(1)}°, {pick.lon.toFixed(1)}°</p>
              <div className="row" style={{ marginTop: 10 }}>
                <button className="btn pri sm" onClick={() => go(pick)}>Analyze region →</button>
                <button className="btn sm xs" onClick={() => setPick(null)} aria-label="Close">×</button>
              </div>
            </div>
          )}
        </Reveal>
      </section>

      <section className="wrap">
        <Reveal><span className="pill">OUR MISSION</span></Reveal>
        <Reveal delay={80}><h2 className="t">Turning Climate Data <span className="g">into Actionable Insights</span></h2></Reveal>
        <Reveal delay={140}><p className="lead" style={{ marginBottom: 26 }}>We combine real-world weather data, transparent statistics and AI narration to help you understand climate risks and track trends.</p></Reveal>
        <div className="grid g4">
          {FEATURES.map(([ic, h, p, to], i) => (
            <Reveal key={h} as={Link} to={to} className="glass feat" delay={i * 90}>
              <div className="fi">{ic}</div><h5>{h}</h5><p className="muted">{p}</p>
            </Reveal>
          ))}
        </div>
        <Reveal><h2 className="t" style={{ marginTop: 56 }}>How it works</h2></Reveal>
        <div className="grid g4 steps" style={{ marginTop: 16 }}>
          {STEPS.map(([h, p], i) => (
            <Reveal key={h} className="glass step" delay={i * 90}>
              <h5 style={{ fontSize: 16, marginBottom: 6 }}>{h}</h5><p className="muted">{p}</p>
            </Reveal>
          ))}
        </div>
        <Reveal style={{ textAlign: 'center', marginTop: 44 }}><Link className="btn pri" to="/dashboard">Open the Dashboard →</Link></Reveal>
      </section>
    </>
  )
}
