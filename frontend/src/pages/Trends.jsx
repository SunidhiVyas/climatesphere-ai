import { useState } from 'react'
import { api } from '../api'
import { MultiLineChart } from '../components/charts'
import { ErrorBox, fmt, HAZARDS, Loading, signed } from '../components/ui'
import { useAsync } from '../state'

const LAST = new Date().getFullYear() - 1
const MAX = 5

export default function Trends() {
  const presets = useAsync(() => api.presets(), [])
  const [chosen, setChosen] = useState(['Delhi', 'Paris', 'Phoenix', 'Sydney'])
  const [hazard, setHazard] = useState('heatwave')
  const [from, setFrom] = useState(1990)
  const [to, setTo] = useState(2020)
  const valid = Number.isInteger(+from) && Number.isInteger(+to) && +from >= 1950 && +to <= LAST && +to - +from >= 4

  const res = useAsync(async (signal) => {
    const items = presets.data.presets.filter(p => chosen.includes(p.name))
    const settled = await Promise.allSettled(items.map(p =>
      api.trends({ region: { name: p.name, lat: p.lat, lon: p.lon }, hazard, from: +from, to: +to, percentile: 95, minDays: '', mode: 'seasonal' }, signal)))
    if (signal.aborted) throw Object.assign(new Error('aborted'), { name: 'AbortError' })
    return items.map((p, i) => ({ name: p.name, a: settled[i].status === 'fulfilled' ? settled[i].value : null, error: settled[i].reason?.message }))
  }, [chosen.join(','), hazard, from, to], !!presets.data && valid && chosen.length > 0)

  const toggle = (n) => setChosen(c => c.includes(n) ? c.filter(x => x !== n) : c.length >= MAX ? c : [...c, n])
  const ok = (res.data || []).filter(r => r.a)

  return (
    <div className="wrap">
      <span className="pill">TRENDS</span>
      <h1 className="t">Compare regions, <span className="g">test the trend</span></h1>
      <p className="lead" style={{ marginBottom: 24 }}>Choose up to {MAX} places. Each is analysed with the same definition, so differences are meaningful. A trend is only called significant when the Mann-Kendall test gives p &lt; 0.05.</p>

      <div className="glass" style={{ marginBottom: 18 }}>
        <div className="grid g4" style={{ alignItems: 'end' }}>
          <div><label className="f" htmlFor="th">HAZARD</label>
            <select id="th" className="in" value={hazard} onChange={e => setHazard(e.target.value)}>{HAZARDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
          <div><label className="f" htmlFor="tf">FROM</label><input id="tf" className="in" type="number" value={from} onChange={e => setFrom(e.target.value)} /></div>
          <div><label className="f" htmlFor="tt">TO</label><input id="tt" className="in" type="number" value={to} onChange={e => setTo(e.target.value)} /></div>
        </div>
        {!valid && <p className="hint" role="alert" style={{ color: '#ffb4ae' }}>Use years between 1950 and {LAST}, at least 5 years apart.</p>}
        <label className="f">REGIONS ({chosen.length}/{MAX})</label>
        <div className="chips">
          {(presets.data?.presets || []).map(p => <button key={p.name} className="chip" aria-pressed={chosen.includes(p.name)} onClick={() => toggle(p.name)}>{p.name}</button>)}
        </div>
      </div>

      {res.loading && <div className="glass"><Loading>Analysing {chosen.length} region(s)… new regions can take 10–40 s each the first time.</Loading></div>}
      {res.error && <ErrorBox error={res.error} />}
      {res.data && (
        <div className="grid">
          {ok.length > 0 && <div className="glass"><h3>{ok[0].a.label.toUpperCase()} DAYS PER YEAR</h3><MultiLineChart items={ok} unit={ok[0].a.units.hazard_days} /></div>}
          <div className="glass">
            <h3>TREND STATISTICS</h3>
            <div className="scrollx">
              <table className="tb">
                <thead><tr><th>Region</th><th>Events</th><th>First → last decade</th><th>Change</th><th>Theil–Sen / decade</th><th>Mann–Kendall p</th><th>Verdict</th></tr></thead>
                <tbody>
                  {res.data.map(r => {
                    if (!r.a) return <tr key={r.name}><td>{r.name}</td><td colSpan={6} style={{ color: '#ffb4ae' }}>{r.error}</td></tr>
                    const t = r.a.trend.hazard_days, dc = t.decade_change
                    return (
                      <tr key={r.name}>
                        <td><b>{r.name}</b></td><td>{r.a.event_count}</td>
                        <td>{fmt(dc.first_mean)} → {fmt(dc.last_mean)}</td>
                        <td>{dc.pct === null ? 'n/a' : signed(dc.pct, 0, '%')}</td>
                        <td>{signed(t.sen.slope_per_decade, 2)}</td>
                        <td>{t.mann_kendall.p === null ? '—' : fmt(t.mann_kendall.p, 3)}</td>
                        <td><span className={`badge ${r.a.insight.significant ? 'warn' : 'mute'}`}>{r.a.insight.significant ? t.mann_kendall.trend.toUpperCase() : 'NO SIGNIFICANT TREND'}</span></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p className="hint">Hazard days per year in the first vs last 10 years of the period. With 5 regions tested, expect about one false positive at p&lt;0.05 by chance alone (multiple comparisons).</p>
          </div>
        </div>
      )}
    </div>
  )
}
