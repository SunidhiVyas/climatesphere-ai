import { useMemo, useState } from 'react'
import { api } from '../api'
import { DecadeChart, FrequencyChart, HazardChart, IntensityChart, SeasonChart } from '../components/charts'
import RegionPicker, { PlaceSearch } from '../components/RegionPicker'
import { ErrorBox, fmt, HAZARD_COLOR, HAZARDS, Kpi, Loading, signed } from '../components/ui'
import { useAsync, useSelection } from '../state'

const LAST = new Date().getFullYear() - 1
const RANGES = [[1990, 2020], [2000, 2020], [1980, 2010], [2005, LAST]]
const PRESETS = [['Delhi', 28.61, 77.21], ['Phoenix', 33.45, -112.07], ['Paris', 48.86, 2.35], ['Sydney', -33.87, 151.21], ['Cairo', 30.04, 31.24], ['São Paulo', -23.55, -46.63]]

export default function Dashboard() {
  const { sel, setSel } = useSelection()
  const [draft, setDraft] = useState(sel)
  const [applied, setApplied] = useState(sel)
  const [nonce, setNonce] = useState(0)
  const set = (p) => setDraft(d => ({ ...d, ...p }))

  const err = useMemo(() => {
    const f = Number(draft.from), t = Number(draft.to)
    if (!Number.isInteger(f) || !Number.isInteger(t)) return 'Enter whole years.'
    if (f < 1950) return 'Data starts in 1950.'
    if (t > LAST) return `The latest complete year is ${LAST}.`
    if (t - f < 4) return 'Choose a range of at least 5 years (10+ recommended for trends).'
    if (draft.region.bbox) {
      const b = draft.region.bbox
      if (![b.south, b.west, b.north, b.east].every(v => v !== '' && Number.isFinite(Number(v)))) return 'Fill in all four box coordinates.'
      if (!(b.south < b.north && b.west < b.east)) return 'Box needs south < north and west < east.'
      if (b.north - b.south > 30 || b.east - b.west > 30) return 'Box too large (max 30° per side).'
    }
    return ''
  }, [draft])

  function analyze(e) {
    e?.preventDefault()
    if (err) return
    const next = { ...draft, from: Number(draft.from), to: Number(draft.to), minDays: draft.minDays === '' ? '' : Number(draft.minDays), percentile: Number(draft.percentile) }
    setApplied(next); setSel(next); setNonce(n => n + 1)
  }

  const st = useAsync((s) => api.trends(applied, s), [JSON.stringify(applied), nonce])
  const a = st.data
  const color = HAZARD_COLOR[applied.hazard]

  return (
    <div className="wrap">
      <span className="pill">DASHBOARD</span>
      <h1 className="t">Climate hazard <span className="g">trend analysis</span></h1>
      <p className="lead" style={{ marginBottom: 26 }}>Pick a place and a period. We fetch ERA5 reanalysis weather, detect hazard events with a percentile rule, and test whether the trend is statistically real.</p>

      <div className="split">
        {/* ---------------- controls ---------------- */}
        <form className="glass" onSubmit={analyze} aria-label="Analysis settings">
          <h3>1 · REGION</h3>
          <PlaceSearch onPick={r => set({ region: r })} />
          <div className="chips" style={{ margin: '12px 0' }}>
            {PRESETS.map(([n, lat, lon]) => <button key={n} type="button" className="chip" onClick={() => set({ region: { name: n, lat, lon } })}>{n}</button>)}
          </div>
          <RegionPicker region={draft.region} onChange={r => set({ region: r })} />
          <p className="muted" style={{ marginTop: 8 }}>Selected: <b style={{ color: 'var(--tx)' }}>{draft.region.name}</b></p>

          <label className="f" htmlFor="hz">HAZARD TYPE</label>
          <select id="hz" className="in" value={draft.hazard} onChange={e => set({ hazard: e.target.value, minDays: '' })}>
            {HAZARDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>

          <label className="f">TIME RANGE</label>
          <div className="row" style={{ flexWrap: 'nowrap' }}>
            <input className="in" type="number" aria-label="From year" value={draft.from} onChange={e => set({ from: e.target.value })} min={1950} max={LAST} />
            <span className="muted">to</span>
            <input className="in" type="number" aria-label="To year" value={draft.to} onChange={e => set({ to: e.target.value })} min={1950} max={LAST} />
          </div>
          <div className="chips" style={{ marginTop: 8 }}>
            {RANGES.map(([f, t]) => <button key={f + '-' + t} type="button" className="chip" aria-pressed={+draft.from === f && +draft.to === t} onClick={() => set({ from: f, to: t })}>{f}–{t}</button>)}
          </div>

          <details className="adv">
            <summary>Detection settings</summary>
            <label className="f" htmlFor="pc">PERCENTILE (default 95)</label>
            <input id="pc" className="in" type="number" min={80} max={99.9} step={0.5} value={draft.percentile} onChange={e => set({ percentile: e.target.value })} />
            <label className="f" htmlFor="md">MIN. CONSECUTIVE DAYS (default per hazard)</label>
            <input id="md" className="in" type="number" min={1} max={30} placeholder={draft.hazard === 'heatwave' ? '3' : draft.hazard === 'rainfall' ? '1' : '15'} value={draft.minDays} onChange={e => set({ minDays: e.target.value })} />
            <label className="f">THRESHOLD TYPE</label>
            <div className="seg">
              <button type="button" aria-pressed={draft.mode === 'seasonal'} onClick={() => set({ mode: 'seasonal' })}>Per calendar day</button>
              <button type="button" aria-pressed={draft.mode === 'annual'} onClick={() => set({ mode: 'annual' })}>One for all days</button>
            </div>
            <p className="hint">Per-calendar-day thresholds compare each day with typical weather for that time of year (recommended). Heatwave only.</p>
          </details>

          {err && <p className="hint" role="alert" style={{ color: '#ffb4ae' }}>{err}</p>}
          <button className="btn pri" type="submit" disabled={!!err || st.loading} style={{ width: '100%', marginTop: 16 }}>
            {st.loading ? <><span className="spin" /> Analysing…</> : 'Analyze →'}
          </button>
        </form>

        {/* ---------------- results ---------------- */}
        <div className="grid" style={{ minWidth: 0 }}>
          {st.loading && !a && <div className="glass"><Loading>Fetching and analysing {applied.to - applied.from + 1} years of daily weather… A new region can take 10–40 s the first time; repeat requests are served from the database cache.</Loading></div>}
          {st.error && <ErrorBox error={st.error} retry={() => setNonce(n => n + 1)} />}
          {a && <Results a={a} color={color} applied={applied} loading={st.loading} />}
        </div>
      </div>
    </div>
  )
}

function Results({ a, color, applied, loading }) {
  const t = a.trend.hazard_days, mk = t.mann_kendall, dc = t.decade_change, sen = t.sen
  const sig = a.insight.significant
  return (
    <div className="grid" style={{ opacity: loading ? .55 : 1, transition: 'opacity .2s' }}>
      <div className="glass insight" style={{ borderColor: sig ? 'rgba(255,112,56,.5)' : undefined }}>
        <div className="row" style={{ marginBottom: 10 }}>
          <span className={`badge ${sig ? 'warn' : 'mute'}`}>{sig ? 'STATISTICALLY SIGNIFICANT' : 'NO SIGNIFICANT TREND'}</span>
          <span className="badge live" title="Served from the MongoDB analyses collection">{a.meta.cache === 'hit' ? 'FROM DB CACHE' : 'FRESHLY COMPUTED'}</span>
          <span className="sp" /><span className="muted">{a.region.name} · {a.label} · {a.period.from}–{a.period.to}</span>
        </div>
        <h2>{a.insight.headline}</h2>
        <ul>{a.insight.bullets.map((b, i) => <li key={i}>{b}</li>)}</ul>
      </div>

      <div className="grid g4">
        <Kpi label="EVENTS DETECTED" value={a.event_count} sub={`${a.period.years_analyzed} years analysed`} color={color} />
        <Kpi label={`CHANGE (LAST VS FIRST ${dc.first_period ? dc.first_period[1] - dc.first_period[0] + 1 : 10} YRS)`} value={dc.pct === null ? 'n/a' : signed(dc.pct, 0, '%')} sub={dc.first_mean !== null ? `${fmt(dc.first_mean)} → ${fmt(dc.last_mean)} ${a.units.hazard_days}` : 'insufficient data'} color={color} />
        <Kpi label="THEIL–SEN SLOPE" value={signed(sen.slope_per_decade, 2)} sub={`${a.units.hazard_days} per decade`} color="#24F0D0" />
        <Kpi label="MANN–KENDALL p" value={mk.p === null ? '—' : fmt(mk.p, 3)} sub={`${mk.trend}${t.reliable ? '' : ' · short series'}`} color={sig ? '#FF7038' : '#A9BED8'} />
      </div>

      <div className="glass"><h3>{a.label.toUpperCase()} DAYS PER YEAR</h3><HazardChart a={a} color={color} /></div>

      <div className="grid g2">
        <div className="glass"><h3>EVENTS PER YEAR & MEAN DURATION</h3><FrequencyChart a={a} /></div>
        {a.units.intensity
          ? <div className="glass"><h3>MEAN INTENSITY</h3><IntensityChart a={a} /></div>
          : <div className="glass"><h3>DECADAL AVERAGE</h3><DecadeChart a={a} /></div>}
        {a.units.intensity && <div className="glass"><h3>DECADAL AVERAGE</h3><DecadeChart a={a} /></div>}
        <div className="glass"><h3>SEASONALITY (EVENT START MONTH)</h3><SeasonChart a={a} /></div>
      </div>

      <div className="glass">
        <h3>LARGEST EVENTS <span className="muted">{a.event_count} detected</span></h3>
        <div className="scrollx">
          <table className="tb">
            <thead><tr><th>Start</th><th>End</th><th>Duration</th><th>{a.hazard === 'heatwave' ? 'Peak Tmax (°C)' : a.hazard === 'rainfall' ? 'Peak (mm)' : 'Length (d)'}</th><th>Intensity</th></tr></thead>
            <tbody>
              {a.events.slice(0, 10).map(e => <tr key={e.start}><td>{e.start}</td><td>{e.end}</td><td>{e.duration} d</td><td>{fmt(e.peak)}</td><td>{e.intensity === null ? '—' : fmt(e.intensity)}</td></tr>)}
              {!a.events.length && <tr><td colSpan={5} className="muted">No events matched the definition in this period.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid g2">
        <div className="glass">
          <h3>METHOD & THRESHOLD</h3>
          <p className="muted" style={{ color: '#dbe7f7' }}>{a.definition.text}</p>
          <p className="hint">Baseline: {a.definition.baseline} · threshold {a.definition.min === a.definition.max ? fmt(a.definition.mean) : `${fmt(a.definition.min)}–${fmt(a.definition.max)}`} {a.definition.unit}</p>
          <ul className="cav">{a.insight.caveats.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </div>
        <div className="glass">
          <h3>DATA QUALITY</h3>
          <table className="tb"><tbody>
            <tr><td>Completeness</td><td>{a.data_quality.completeness_pct}%</td></tr>
            <tr><td>Missing days (raw)</td><td>{a.data_quality.missing_raw.tmax}</td></tr>
            <tr><td>Short gaps interpolated</td><td>{a.data_quality.interpolated_days}</td></tr>
            <tr><td>Out-of-range values removed</td><td>{a.data_quality.out_of_range}</td></tr>
            <tr><td>Tmin &gt; Tmax removed</td><td>{a.data_quality.inconsistent_tmax_tmin}</td></tr>
            <tr><td>Outlier spikes removed</td><td>{a.data_quality.spikes_removed}</td></tr>
            <tr><td>Years excluded (&lt;90% coverage)</td><td>{a.period.years_excluded.length ? a.period.years_excluded.join(', ') : 'none'}</td></tr>
          </tbody></table>
          <p className="hint">Source: <a href={a.source.url} target="_blank" rel="noreferrer" style={{ color: 'var(--cy)' }}>{a.source.name}</a></p>
        </div>
      </div>

      <div className="glass">
        <h3>EXPORT</h3>
        <div className="row">
          <a className="btn sm" href={api.exportUrl('csv', applied)}>⬇ Annual CSV</a>
          <a className="btn sm" href={api.exportUrl('csv', applied, { kind: 'events' })}>⬇ Events CSV</a>
          <a className="btn sm" href={api.exportUrl('pdf', applied)}>⬇ PDF report</a>
          <a className="btn sm" href={api.exportUrl('png', applied)} target="_blank" rel="noreferrer">🖼 Trend plot (PNG)</a>
        </div>
      </div>
    </div>
  )
}
