import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import fx from './fixtures/api.json'

// jsdom has no WebGL / canvas / real maps -> stub the heavy visual widgets (their data flow is still tested)
vi.mock('../components/Globe', () => ({ default: ({ overlay, hotspots }) => <div data-testid="globe">{hotspots.length} hotspots {overlay ? 'overlay:' + overlay.name : ''}</div> }))
vi.mock('react-chartjs-2', () => ({ Chart: ({ data }) => <div data-testid="chart">{data.datasets.length} datasets</div> }))
vi.mock('react-leaflet', () => ({ MapContainer: ({ children }) => <div data-testid="map">{children}</div>, TileLayer: () => null, CircleMarker: () => null, Rectangle: () => null, useMap: () => ({ getZoom: () => 4, setView() {}, fitBounds() {} }), useMapEvents: () => null }))
vi.mock('leaflet/dist/leaflet.css', () => ({}))

import { SelectionProvider } from '../state'
import AILab from '../pages/AILab'
import Dashboard from '../pages/Dashboard'
import Explore from '../pages/Explore'
import Home from '../pages/Home'
import Reports from '../pages/Reports'
import Trends from '../pages/Trends'

const calls = []
beforeEach(() => {
  calls.length = 0
  localStorage.clear()
  globalThis.fetch = vi.fn(async (url) => {
    const u = new URL(url, 'http://x'); calls.push(u.pathname + u.search)
    const map = {
      '/api/trends': u.searchParams.get('hazard') === 'drought' ? fx.trends_drought : fx.trends, '/api/summary': fx.summary, '/api/projections': fx.projections,
      '/api/insights': fx.insights, '/api/aerosol': fx.aerosol, '/api/impact': fx.impact, '/api/layer': fx.layer, '/api/presets': fx.presets,
      '/api/health': fx.health, '/api/region': fx.region,
    }
    const body = map[u.pathname]
    return body ? { ok: true, status: 200, json: async () => body } : { ok: false, status: 404, json: async () => ({ error: 'nf' }) }
  })
})
const wrap = (ui) => render(<MemoryRouter><SelectionProvider>{ui}</SelectionProvider></MemoryRouter>)

test('Home shows live pipeline status and globe hotspots', async () => {
  wrap(<Home />)
  await waitFor(() => screen.getByText(/in-memory/i))
  await waitFor(() => expect(screen.getByTestId('globe').textContent).toContain('12 hotspots'))
})

test('Dashboard renders insight, KPIs, charts, events, quality and export links from /api/trends', async () => {
  wrap(<Dashboard />)
  await waitFor(() => screen.getByText(fx.trends.insight.headline))
  expect(screen.getAllByTestId('chart').length).toBeGreaterThanOrEqual(4)
  expect(screen.getByText(/MANN–KENDALL p/)).toBeTruthy()
  expect(screen.getByText(/DATA QUALITY/)).toBeTruthy()
  const csv = screen.getByText(/Annual CSV/).getAttribute('href')
  expect(csv).toContain('/api/export/csv') ; expect(csv).toContain('lat=28.61') ; expect(csv).toContain('from=1990')
  expect(calls.some(c => c.startsWith('/api/trends'))).toBe(true)
})

test('Dashboard validates the time range client-side and blocks Analyze', async () => {
  wrap(<Dashboard />)
  await waitFor(() => screen.getByText(fx.trends.insight.headline))
  fireEvent.change(screen.getByLabelText('To year'), { target: { value: '1992' } })
  expect(screen.getByRole('alert').textContent).toMatch(/at least 5 years/)
  expect(screen.getByRole('button', { name: /Analyze/ }).disabled).toBe(true)
})

test('Dashboard handles a hazard without intensity (drought) without crashing', async () => {
  localStorage.setItem('cs.sel', JSON.stringify({ hazard: 'drought' }))
  wrap(<Dashboard />)
  await waitFor(() => screen.getByText(fx.trends_drought.insight.headline))
})

test('Dashboard shows API errors to the user', async () => {
  globalThis.fetch = vi.fn(async () => ({ ok: false, status: 502, json: async () => ({ error: 'Data provider problem: Upstream busy' }) }))
  wrap(<Dashboard />)
  await waitFor(() => screen.getByText(/Upstream busy/))
})

test('Trends compares regions and lists Mann-Kendall statistics', async () => {
  wrap(<Trends />)
  await waitFor(() => screen.getByText('TREND STATISTICS'))
  expect(calls.filter(c => c.startsWith('/api/trends')).length).toBe(4)
})

test('Explore loads a live layer onto the globe', async () => {
  wrap(<Explore />)
  await waitFor(() => expect(screen.getByTestId('globe').textContent).toContain('overlay:temp'))
})

test('AI Lab shows projections + insight text', async () => {
  wrap(<AILab />)
  await waitFor(() => screen.getByText(fx.insights.text))
  expect(screen.getAllByText(/SSP5-8.5/).length).toBeGreaterThan(0)
  expect(screen.getByText('WARMING')).toBeTruthy()
})

test('Reports shows World Bank indicators and build links', async () => {
  wrap(<Reports />)
  await waitFor(() => screen.getByText(new RegExp(fx.impact.indicators[0].label, 'i')))
  expect(screen.getByText(/⬇ PDF/).getAttribute('href')).toContain('/api/export/pdf')
})
