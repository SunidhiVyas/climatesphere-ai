import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'

const LINKS = [['/', 'Home'], ['/dashboard', 'Dashboard'], ['/explore', 'Explore'], ['/trends', 'Trends'], ['/ai-lab', 'AI Lab'], ['/reports', 'Reports']]

export default function Header() {
  const [open, setOpen] = useState(false)
  return (
    <header className="hdr">
      <Link className="brand" to="/" aria-label="ClimateSphere AI home">
        <span className="logo" />
        <span><b>Climate<i>Sphere</i> AI</b><small>CLIMATE HAZARD TREND ANALYZER</small></span>
      </Link>
      <nav className={`main ${open ? 'open' : ''}`} aria-label="Main" onClick={() => setOpen(false)}>
        {LINKS.map(([to, label]) => <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => (isActive ? 'active' : '')}>{label}</NavLink>)}
      </nav>
      <div className="row">
        <Link className="btn sm" to="/dashboard">Get Started →</Link>
        <button className="burger" aria-label="Menu" aria-expanded={open} onClick={() => setOpen(o => !o)}>
          <svg width="24" height="24" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" fill="none"><path d="M3 6h18M3 12h18M3 18h18" /></svg>
        </button>
      </div>
    </header>
  )
}
