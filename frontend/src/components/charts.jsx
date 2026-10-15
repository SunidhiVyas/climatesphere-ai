import {
  BarController, BarElement, CategoryScale, Chart as ChartJS, Filler, Legend, LineController, LineElement,
  LinearScale, PointElement, Tooltip,
} from 'chart.js'
import { Chart } from 'react-chartjs-2'

ChartJS.register(BarController, BarElement, CategoryScale, Filler, Legend, LineController, LineElement, LinearScale, PointElement, Tooltip)
ChartJS.defaults.color = '#A9BED8'
ChartJS.defaults.font.family = 'Inter, system-ui, sans-serif'

const grid = { color: 'rgba(169,190,216,.1)' }
const base = (yTitle, extra = {}) => ({
  responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, spanGaps: false,
  plugins: { legend: { labels: { boxWidth: 12, usePointStyle: true } }, tooltip: { backgroundColor: 'rgba(2,8,19,.95)', borderColor: 'rgba(0,229,255,.4)', borderWidth: 1 } },
  scales: {
    x: { grid: { display: false }, ticks: { maxTicksLimit: 12 } },
    y: { grid, beginAtZero: true, title: { display: !!yTitle, text: yTitle } },
    ...extra,
  },
})

/** Annual hazard days (bars) + 5-year rolling mean + OLS trend line. `null` = year excluded (low coverage) -> gap. */
export function HazardChart({ a, color = '#FF7038' }) {
  const data = {
    labels: a.years,
    datasets: [
      { type: 'bar', label: a.units.hazard_days, data: a.series.hazard_days, backgroundColor: color + 'cc', borderRadius: 3, order: 3 },
      { type: 'line', label: `${a.rolling.window}-yr rolling mean`, data: a.rolling.hazard_days, borderColor: '#00E5FF', backgroundColor: '#00E5FF', borderWidth: 2.5, pointRadius: 0, tension: .35, order: 1 },
      { type: 'line', label: 'Linear trend (OLS)', data: a.fit.hazard_days, borderColor: '#F5F9FF', borderDash: [6, 5], borderWidth: 1.6, pointRadius: 0, order: 2 },
    ],
  }
  return <div className="chartbox"><Chart type="bar" data={data} options={base(a.units.hazard_days)} /></div>
}

/** Events per year (bars) + mean duration (line, right axis). */
export function FrequencyChart({ a }) {
  const data = {
    labels: a.years,
    datasets: [
      { type: 'bar', label: a.units.frequency, data: a.series.frequency, backgroundColor: '#2196FFcc', borderRadius: 3, yAxisID: 'y' },
      { type: 'line', label: `Mean duration (${a.units.duration})`, data: a.series.duration, borderColor: '#24F0D0', backgroundColor: '#24F0D0', pointRadius: 3, borderWidth: 2, tension: .25, yAxisID: 'y2' },
    ],
  }
  const opts = base(a.units.frequency, { y2: { position: 'right', grid: { display: false }, beginAtZero: true, title: { display: true, text: a.units.duration } } })
  return <div className="chartbox sm"><Chart type="bar" data={data} options={opts} /></div>
}

export function IntensityChart({ a }) {
  const data = {
    labels: a.years,
    datasets: [{ type: 'line', label: a.units.intensity, data: a.series.intensity, borderColor: '#FFC857', backgroundColor: '#FFC85733', fill: true, pointRadius: 3, tension: .25 }],
  }
  return <div className="chartbox sm"><Chart type="line" data={data} options={base(a.units.intensity)} /></div>
}

export function DecadeChart({ a }) {
  const data = {
    labels: a.decades.map(d => d.label),
    datasets: [{ type: 'bar', label: a.units.hazard_days, data: a.decades.map(d => d.hazard_days_per_year), backgroundColor: ['#2196FF', '#00E5FF', '#24F0D0', '#FFC857', '#FF7038', '#FF3D32'].map(c => c + 'cc'), borderRadius: 6 }],
  }
  return <div className="chartbox sm"><Chart type="bar" data={data} options={{ ...base(a.units.hazard_days), plugins: { legend: { display: false } } }} /></div>
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
export function SeasonChart({ a }) {
  const data = { labels: MONTHS, datasets: [{ type: 'bar', label: 'Events starting in month', data: a.seasonality, backgroundColor: '#A970FFcc', borderRadius: 4 }] }
  return <div className="chartbox sm"><Chart type="bar" data={data} options={{ ...base('events'), plugins: { legend: { display: false } } }} /></div>
}

const PALETTE = ['#FF7038', '#00E5FF', '#24F0D0', '#A970FF', '#FFC857', '#2196FF']
/** Several regions on one axis: 5-year rolling mean of hazard days. */
export function MultiLineChart({ items, unit }) {
  const years = items[0]?.a.years || []
  const data = {
    labels: years,
    datasets: items.map((it, i) => ({
      type: 'line', label: it.name, data: it.a.rolling.hazard_days, borderColor: PALETTE[i % PALETTE.length],
      backgroundColor: PALETTE[i % PALETTE.length], borderWidth: 2.5, pointRadius: 0, tension: .35,
    })),
  }
  return <div className="chartbox"><Chart type="line" data={data} options={base(`${unit} (5-yr rolling mean)`)} /></div>
}
