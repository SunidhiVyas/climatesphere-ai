import { useEffect, useState } from 'react'
import { CircleMarker, MapContainer, Rectangle, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { api } from '../api'

const TILE_URL = import.meta.env.VITE_TILE_URL ||
  'https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}'
const TILE_ATTR = import.meta.env.VITE_TILE_ATTRIBUTION ||
  'Tiles &copy; <a href="https://www.esri.com/">Esri</a> &mdash; Esri, HERE, Garmin, &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'

/** City / place search backed by /api/region (Open-Meteo geocoding, cached in MongoDB). */
export function PlaceSearch({ onPick, placeholder = 'Search a city, region or country…' }) {
  const [q, setQ] = useState('')
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function submit(e) {
    e.preventDefault()
    if (q.trim().length < 2) return
    setBusy(true); setErr(''); setRes(null)
    try {
      const j = await api.region(q.trim())
      if (j.results.length === 1) { onPick({ name: j.results[0].name, lat: j.results[0].lat, lon: j.results[0].lon }); setQ('') } else setRes(j.results)
    } catch (ex) { setErr(ex.message) } finally { setBusy(false) }
  }
  return (
    <form onSubmit={submit} className="dd" role="search">
      <div className="row" style={{ flexWrap: 'nowrap' }}>
        <input className="in" value={q} onChange={e => setQ(e.target.value)} placeholder={placeholder} aria-label="Search a place" maxLength={80} />
        <button className="btn sm" type="submit" disabled={busy}>{busy ? <span className="spin" /> : 'Find'}</button>
      </div>
      {err && <p className="hint" role="alert" style={{ color: '#ffb4ae' }}>{err}</p>}
      {res && (
        <ul role="listbox">
          {res.map((r, i) => (
            <li key={i}><button type="button" onClick={() => { onPick({ name: r.name, lat: r.lat, lon: r.lon }); setRes(null); setQ('') }}>{r.label}</button></li>
          ))}
        </ul>
      )}
    </form>
  )
}

function Clicks({ onClick }) { useMapEvents({ click: e => onClick(e.latlng) }); return null }
function View({ region }) {
  const map = useMap()
  const key = region.bbox ? JSON.stringify(region.bbox) : `${region.lat},${region.lon}`
  useEffect(() => {
    if (region.bbox) map.fitBounds([[region.bbox.south, region.bbox.west], [region.bbox.north, region.bbox.east]], { padding: [20, 20] })
    else map.setView([region.lat, region.lon], Math.max(map.getZoom(), 4))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  return null
}

const r2 = (x) => Math.round(x * 100) / 100

/** Map-based selection: click for a point, or switch to "Box" and click two opposite corners. */
export default function RegionPicker({ region, onChange }) {
  const [mode, setMode] = useState(region.bbox ? 'box' : 'point')
  const [corner, setCorner] = useState(null)
  const [msg, setMsg] = useState('')

  function click({ lat, lng }) {
    setMsg('')
    if (mode === 'point') { onChange({ name: `${r2(lat)}°, ${r2(lng)}°`, lat: r2(lat), lon: r2(((lng + 540) % 360) - 180) }); return }
    if (!corner) { setCorner({ lat, lng }); return }
    const s = Math.min(lat, corner.lat), n = Math.max(lat, corner.lat), w = Math.min(lng, corner.lng), e = Math.max(lng, corner.lng)
    setCorner(null)
    if (n - s > 30 || e - w > 30) { setMsg('Box too large - maximum 30° per side.'); return }
    if (n - s < .2 || e - w < .2) { setMsg('Box too small - pick two corners further apart.'); return }
    onChange({ name: 'Custom box', lat: r2((s + n) / 2), lon: r2((w + e) / 2), bbox: { south: r2(s), west: r2(w), north: r2(n), east: r2(e) } })
  }
  function setBox(k, v) {
    const b = { ...region.bbox, [k]: v === '' ? '' : Number(v) }
    onChange({ ...region, bbox: b })
  }
  function switchMode(m) {
    setMode(m); setCorner(null); setMsg('')
    if (m === 'point' && region.bbox) onChange({ name: region.name === 'Custom box' ? `${region.lat}°, ${region.lon}°` : region.name, lat: region.lat, lon: region.lon })
  }

  return (
    <div>
      <div className="seg" role="group" aria-label="Selection mode" style={{ marginBottom: 10 }}>
        <button type="button" aria-pressed={mode === 'point'} onClick={() => switchMode('point')}>City / point</button>
        <button type="button" aria-pressed={mode === 'box'} onClick={() => switchMode('box')}>Lat-lon box</button>
      </div>
      <div className="mapbox">
        <MapContainer center={[region.lat, region.lon]} zoom={4} minZoom={2} worldCopyJump style={{ height: '100%', width: '100%' }} attributionControl>
          <TileLayer url={TILE_URL} subdomains="abcd" maxZoom={12} attribution={TILE_ATTR} />
          <Clicks onClick={click} />
          <View region={region} />
          {region.bbox
            ? <Rectangle bounds={[[region.bbox.south, region.bbox.west], [region.bbox.north, region.bbox.east]]} pathOptions={{ color: '#00E5FF', weight: 2, fillOpacity: .12 }} />
            : <CircleMarker center={[region.lat, region.lon]} radius={8} pathOptions={{ color: '#24F0D0', fillColor: '#00E5FF', fillOpacity: .9 }} />}
          {corner && <CircleMarker center={[corner.lat, corner.lng]} radius={5} pathOptions={{ color: '#FFC857' }} />}
        </MapContainer>
      </div>
      <p className="hint">{mode === 'point' ? 'Click the map to choose a location.' : corner ? 'Now click the opposite corner.' : 'Click two opposite corners of the area (max 30° per side).'}</p>
      {msg && <p className="hint" role="alert" style={{ color: '#ffb4ae' }}>{msg}</p>}
      {mode === 'box' && region.bbox && (
        <div className="grid g2" style={{ gap: 8, marginTop: 8 }}>
          {[['south', 'South °'], ['north', 'North °'], ['west', 'West °'], ['east', 'East °']].map(([k, l]) => (
            <label key={k} className="f" style={{ margin: 0 }}>{l}
              <input className="in" type="number" step="0.5" value={region.bbox[k]} onChange={e => setBox(k, e.target.value)} />
            </label>
          ))}
        </div>
      )}
    </div>
  )
}
