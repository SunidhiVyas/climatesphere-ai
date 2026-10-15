import { lazy, Suspense } from 'react'
import { HashRouter, Route, Routes } from 'react-router-dom'
import Footer from './components/Footer'
import Header from './components/Header'
import { Loading } from './components/ui'
import { SelectionProvider } from './state'

// Route-level code splitting keeps three.js / leaflet / chart.js out of the first paint.
const Home = lazy(() => import('./pages/Home'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Explore = lazy(() => import('./pages/Explore'))
const Trends = lazy(() => import('./pages/Trends'))
const AILab = lazy(() => import('./pages/AILab'))
const Reports = lazy(() => import('./pages/Reports'))

export default function App() {
  return (
    <HashRouter>
      <SelectionProvider>
        <Header />
        <main className="page">
          <Suspense fallback={<div className="wrap"><Loading /></div>}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/explore" element={<Explore />} />
            <Route path="/trends" element={<Trends />} />
            <Route path="/ai-lab" element={<AILab />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="*" element={<Home />} />
          </Routes>
          </Suspense>
        </main>
        <Footer />
      </SelectionProvider>
    </HashRouter>
  )
}
