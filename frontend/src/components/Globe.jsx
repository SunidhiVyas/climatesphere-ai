import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { geoEquirectangular, geoGraticule10, geoPath } from 'd3-geo'
import { feature, mesh } from 'topojson-client'
import countries from 'world-atlas/countries-110m.json'

const R = 1
// Same convention as THREE.SphereGeometry so an equirectangular texture lines up.
export function latLonToVec3(lat, lon, r = R) {
  const phi = ((lon + 180) * Math.PI) / 180, th = ((90 - lat) * Math.PI) / 180
  return new THREE.Vector3(-r * Math.cos(phi) * Math.sin(th), r * Math.cos(th), r * Math.sin(phi) * Math.sin(th))
}
export function vec3ToLatLon(p) {
  const r = p.length(), colat = Math.acos(p.y / r)
  let lon = (Math.atan2(p.z, -p.x) * 180) / Math.PI - 180
  if (lon < -180) lon += 360
  return { lat: 90 - (colat * 180) / Math.PI, lon }
}

// colour ramps for live layers: v in 0..1 -> [r,g,b,a]
const lerp = (a, b, t) => a.map((x, i) => x + (b[i] - x) * t)
function ramp(stops, v) {
  const t = Math.min(Math.max(v, 0), 0.9999) * (stops.length - 1), i = Math.floor(t)
  return lerp(stops[i], stops[i + 1], t - i)
}
const RAMPS = {
  temp: [[33, 100, 255, 190], [0, 229, 255, 170], [120, 240, 160, 150], [255, 214, 80, 190], [255, 107, 53, 215], [255, 40, 40, 235]],
  rain: [[0, 150, 255, 0], [0, 190, 255, 140], [80, 120, 255, 200], [169, 112, 255, 240]],
  wind: [[36, 240, 208, 0], [36, 240, 208, 150], [255, 255, 255, 220]],
  cloud: [[255, 255, 255, 0], [255, 255, 255, 120], [255, 255, 255, 220]],
  dry: [[255, 200, 87, 0], [255, 160, 60, 150], [200, 80, 30, 230]],
}

function buildTexture(overlay) {
  const W = 2048, H = 1024
  const c = document.createElement('canvas'); c.width = W; c.height = H
  const ctx = c.getContext('2d')
  const g = ctx.createLinearGradient(0, 0, 0, H)
  g.addColorStop(0, '#07305e'); g.addColorStop(.5, '#06274f'); g.addColorStop(1, '#07305e')
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H)
  const proj = geoEquirectangular().scale(W / (2 * Math.PI)).translate([W / 2, H / 2])
  const path = geoPath(proj, ctx)
  ctx.beginPath(); path(geoGraticule10()); ctx.strokeStyle = 'rgba(0,229,255,.10)'; ctx.lineWidth = 1; ctx.stroke()
  ctx.beginPath(); path(feature(countries, countries.objects.countries)); ctx.fillStyle = '#0f4a6e'; ctx.fill()
  if (overlay?.values && RAMPS[overlay.name]) {
    const { width: w, height: h, values } = overlay
    const tiny = document.createElement('canvas'); tiny.width = w; tiny.height = h
    const tctx = tiny.getContext('2d'), img = tctx.createImageData(w, h)
    values.forEach((v, k) => {
      const col = v === null ? [0, 0, 0, 0] : ramp(RAMPS[overlay.name], v)
      img.data.set(col.map(Math.round), k * 4)
    })
    tctx.putImageData(img, 0, 0)
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high'
    ctx.drawImage(tiny, 0, 0, W, H)   // bilinear upscaling smooths the 10° grid
  }
  ctx.beginPath(); path(mesh(countries, countries.objects.countries, (a, b) => a !== b)); ctx.strokeStyle = 'rgba(0,229,255,.45)'; ctx.lineWidth = 1; ctx.stroke()
  ctx.beginPath(); path(feature(countries, countries.objects.countries)); ctx.strokeStyle = 'rgba(0,229,255,.55)'; ctx.lineWidth = 1.2; ctx.stroke()
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 8
  return tex
}

/**
 * props: hotspots [{name,lat,lon}], selected {lat,lon}|null, overlay {name,values,width,height}|null,
 *        onHotspot(h), onPick({lat,lon}), autoRotate
 */
export default function Globe({ hotspots = [], selected = null, overlay = null, onHotspot, onPick, autoRotate = true }) {
  const host = useRef(null)
  const api = useRef({})
  const cb = useRef({})
  cb.current = { onHotspot, onPick }
  const [tip, setTip] = useState(null)
  const [fail, setFail] = useState(false)

  useEffect(() => {
    const el = host.current
    let renderer
    try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true }) } catch { setFail(true); return }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    el.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(40, 1, .1, 100)
    camera.position.set(0, 0.5, 3.2)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enablePan = false; controls.enableDamping = true; controls.minDistance = 1.9; controls.maxDistance = 4.5
    controls.autoRotate = autoRotate; controls.autoRotateSpeed = 0.5

    const globe = new THREE.Mesh(new THREE.SphereGeometry(R, 96, 64), new THREE.MeshBasicMaterial({ map: buildTexture(null) }))
    scene.add(globe)
    const glow = new THREE.Mesh(new THREE.SphereGeometry(R * 1.14, 64, 48), new THREE.ShaderMaterial({
      transparent: true, side: THREE.BackSide, blending: THREE.AdditiveBlending, depthWrite: false,
      vertexShader: 'varying vec3 vN;void main(){vN=normalize(normalMatrix*normal);gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',
      fragmentShader: 'varying vec3 vN;void main(){float i=pow(max(0.72-dot(vN,vec3(0.,0.,1.)),0.),3.);gl_FragColor=vec4(0.,.85,1.,1.)*i*1.6;}',
    }))
    scene.add(glow)
    const stars = new THREE.Points(
      new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(Array.from({ length: 900 }, () => (Math.random() - .5) * 40), 3)),
      new THREE.PointsMaterial({ color: 0x9fd8ff, size: .03, transparent: true, opacity: .7 }))
    scene.add(stars)

    const markers = new THREE.Group(); globe.add(markers)
    const selMarker = new THREE.Mesh(new THREE.SphereGeometry(.025, 16, 16), new THREE.MeshBasicMaterial({ color: 0x24f0d0 }))
    selMarker.visible = false; globe.add(selMarker)
    const ring = new THREE.Mesh(new THREE.RingGeometry(.035, .045, 32), new THREE.MeshBasicMaterial({ color: 0x24f0d0, side: THREE.DoubleSide, transparent: true }))
    ring.visible = false; globe.add(ring)

    const ray = new THREE.Raycaster(), ndc = new THREE.Vector2()
    const setNdc = (e) => { const r = renderer.domElement.getBoundingClientRect(); ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1); ray.setFromCamera(ndc, camera) }
    const hitHotspot = () => ray.intersectObjects(markers.children, true)[0]?.object.userData.h
    let down = null, resume
    const onDown = (e) => { down = { x: e.clientX, y: e.clientY }; controls.autoRotate = false; clearTimeout(resume) }
    const onUp = (e) => {
      resume = setTimeout(() => { controls.autoRotate = api.current.auto }, 5000)
      if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) return   // it was a drag
      setNdc(e)
      const h = hitHotspot()
      if (h) { cb.current.onHotspot?.(h); return }
      const hit = ray.intersectObject(globe, false)[0]
      if (hit) cb.current.onPick?.(vec3ToLatLon(globe.worldToLocal(hit.point.clone())))
    }
    const onMove = (e) => {
      setNdc(e); const h = hitHotspot()
      renderer.domElement.style.cursor = h ? 'pointer' : ''
      const r = el.getBoundingClientRect()
      setTip(h ? { x: e.clientX - r.left, y: e.clientY - r.top, text: h.name } : null)
    }
    const cv = renderer.domElement
    cv.addEventListener('pointerdown', onDown); cv.addEventListener('pointerup', onUp); cv.addEventListener('pointermove', onMove)

    const resize = () => { const w = el.clientWidth || 400, h = el.clientHeight || 400; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix() }
    const ro = new ResizeObserver(resize); ro.observe(el); resize()

    let raf, t0 = performance.now()
    const loop = (t) => {
      raf = requestAnimationFrame(loop)
      controls.update()
      const k = 1 + .25 * Math.sin((t - t0) / 350)
      markers.children.forEach(m => m.scale.setScalar(k))
      if (ring.visible) { ring.scale.setScalar(1 + ((t - t0) % 1400) / 1400); ring.material.opacity = 1 - ((t - t0) % 1400) / 1400 }
      renderer.render(scene, camera)
    }
    loop(t0)

    api.current = { globe, markers, selMarker, ring, controls, auto: autoRotate }
    return () => {
      cancelAnimationFrame(raf); clearTimeout(resume); ro.disconnect()
      cv.removeEventListener('pointerdown', onDown); cv.removeEventListener('pointerup', onUp); cv.removeEventListener('pointermove', onMove)
      controls.dispose(); renderer.dispose()
      scene.traverse(o => { o.geometry?.dispose?.(); o.material?.map?.dispose?.(); o.material?.dispose?.() })
      el.removeChild(renderer.domElement)
    }
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  // hotspots
  useEffect(() => {
    const { markers } = api.current
    if (!markers) return
    markers.clear()
    hotspots.forEach(h => {
      const m = new THREE.Mesh(new THREE.SphereGeometry(.022, 16, 16), new THREE.MeshBasicMaterial({ color: 0xff6b35 }))
      m.position.copy(latLonToVec3(h.lat, h.lon, R * 1.005)); m.userData.h = h
      const hit = new THREE.Mesh(new THREE.SphereGeometry(.06, 8, 8), new THREE.MeshBasicMaterial({ visible: false }))
      hit.userData.h = h; m.add(hit); markers.add(m)
    })
  }, [hotspots])

  // selected marker
  useEffect(() => {
    const { selMarker, ring } = api.current
    if (!selMarker) return
    if (!selected) { selMarker.visible = ring.visible = false; return }
    const p = latLonToVec3(selected.lat, selected.lon, R * 1.006)
    selMarker.position.copy(p); ring.position.copy(latLonToVec3(selected.lat, selected.lon, R * 1.008))
    ring.lookAt(p.clone().multiplyScalar(2))
    selMarker.visible = ring.visible = true
  }, [selected])

  // data overlay -> redraw texture
  useEffect(() => {
    const { globe } = api.current
    if (!globe) return
    const old = globe.material.map
    globe.material.map = buildTexture(overlay); globe.material.needsUpdate = true
    old?.dispose()
  }, [overlay])

  useEffect(() => { if (api.current.controls) { api.current.auto = autoRotate; api.current.controls.autoRotate = autoRotate } }, [autoRotate])

  if (fail) return <div className="glass state">3D view needs WebGL, which is not available in this browser. Use the region search instead.</div>
  return (
    <div className="globe" ref={host} role="img" aria-label="Interactive 3D Earth. Drag to rotate; click a marker or anywhere on the globe to choose a location.">
      {tip && <div className="gtip" style={{ left: tip.x, top: tip.y }}>{tip.text}</div>}
    </div>
  )
}
