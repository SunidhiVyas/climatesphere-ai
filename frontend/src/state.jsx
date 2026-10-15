import { createContext, useContext, useEffect, useMemo, useState } from 'react'

export const DEFAULT_SEL = {
  region: { name: 'Delhi', lat: 28.61, lon: 77.21 },
  hazard: 'heatwave', from: 1990, to: 2020, percentile: 95, minDays: '', mode: 'seasonal',
}
const Ctx = createContext(null)

// Selection (region / hazard / period) is shared by every page and kept in localStorage.
export function SelectionProvider({ children }) {
  const [sel, setSel] = useState(() => {
    try { return { ...DEFAULT_SEL, ...JSON.parse(localStorage.getItem('cs.sel') || '{}') } } catch { return DEFAULT_SEL }
  })
  useEffect(() => { try { localStorage.setItem('cs.sel', JSON.stringify(sel)) } catch { /* private mode */ } }, [sel])
  const value = useMemo(() => ({ sel, setSel, patch: (p) => setSel(s => ({ ...s, ...p })) }), [sel])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
export const useSelection = () => useContext(Ctx)

/** Run an async loader whenever `deps` change; ignores stale responses and aborts in-flight requests. */
export function useAsync(loader, deps, enabled = true) {
  const [st, setSt] = useState({ data: null, error: null, loading: enabled })
  useEffect(() => {
    if (!enabled) { setSt({ data: null, error: null, loading: false }); return }
    const ac = new AbortController()
    setSt(s => ({ data: s.data, error: null, loading: true }))
    loader(ac.signal)
      .then(data => { if (!ac.signal.aborted) setSt({ data, error: null, loading: false }) })
      .catch(error => { if (error.name !== 'AbortError') setSt({ data: null, error, loading: false }) })
    return () => ac.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled])
  return st
}
