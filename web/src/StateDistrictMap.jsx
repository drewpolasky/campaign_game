import { useEffect, useMemo, useState } from 'react'
import { seatName, supportPercents } from './players.js'

// Hover tooltip for a district — mirrors CampaignGame.format_district_tooltip:
// name + delegates, the leader, and each candidate's support % and polling %.
function districtTooltip(state, d) {
  const lines = [`${d.name} — ${d.population} delegates`]
  const pcts = supportPercents(d.support)
  if (pcts.length) {
    const leader = d.support.indexOf(Math.max(...d.support))
    lines.push(`Leader: ${seatName(state, leader + 1)}`)
    pcts.forEach((p, i) => {
      const poll = d.polling_average?.[i]
      lines.push(`  ${seatName(state, i + 1)}: ${p.toFixed(1)}% support${poll != null ? `  (polling ${poll}%)` : ''}`)
    })
  } else {
    lines.push('No support yet')
  }
  return lines.join('\n')
}

// Renders a state's district boundaries (vectorized from the game's pixel maps
// by scripts/build_district_geo.py, served from /districts/<State>.json).
// Each district is filled by its current leader and is clickable.
export default function StateDistrictMap({ stateName, state, idx, seatColors, selectedDistrict, onSelectDistrict }) {
  const [geo, setGeo] = useState(null)
  const [err, setErr] = useState(false)

  useEffect(() => {
    let live = true
    setGeo(null); setErr(false)
    fetch(`/districts/${encodeURIComponent(stateName)}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((g) => live && setGeo(g))
      .catch(() => live && setErr(true))
    return () => { live = false }
  }, [stateName])

  const st = state.states[stateName]
  const byName = useMemo(() => {
    const m = {}
    for (const d of st.districts) {
      const p = d.polling_average
      let leader = null
      if (p && p.length && !p.every((x) => x === 0)) leader = p.indexOf(Math.max(...p))
      m[d.name.trim()] = { leader, district: d }
    }
    return m
  }, [st])

  if (err) return <p className="muted small">No district map for {stateName}. Use the list on the right to allocate.</p>
  if (!geo) return <p className="muted small">Loading {stateName} districts…</p>

  const [vx, vy, vw, vh] = geo.viewBox
  return (
    <svg viewBox={`${vx} ${vy} ${vw} ${vh}`} className="district-map" role="img" aria-label={`${stateName} districts`}>
      {Object.entries(geo.districts).map(([name, polys]) => {
        const info = byName[name.trim()] || {}
        const fill = info.leader != null ? seatColors[info.leader] : '#39445c'
        const sel = selectedDistrict === name.trim()
        return polys.map((poly, i) => (
          <polygon key={name + i} points={poly.map((p) => p.join(',')).join(' ')}
            fill={fill} fillOpacity={sel ? 1 : 0.78}
            stroke={sel ? '#ffffff' : '#0f1420'} strokeWidth={sel ? 2.2 : 1}
            style={{ cursor: 'pointer' }}
            onClick={() => onSelectDistrict(name.trim())}>
            <title>{info.district ? districtTooltip(state, info.district) : name}</title>
          </polygon>
        ))
      })}
    </svg>
  )
}
