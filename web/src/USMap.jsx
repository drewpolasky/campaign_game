import { useMemo } from 'react'
import { feature } from 'topojson-client'
import { geoAlbersUsa, geoPath } from 'd3-geo'
import statesTopo from 'us-atlas/states-10m.json'
import { seatName, supportPercents } from './players.js'

const W = 960, H = 600

// Multiply a hex color toward black — used to dim states that have voted.
function darken(hex, f) {
  const n = parseInt(hex.slice(1), 16)
  const r = Math.round(((n >> 16) & 255) * f)
  const g = Math.round(((n >> 8) & 255) * f)
  const b = Math.round((n & 255) * f)
  return '#' + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)
}

// Hover tooltip for a state — mirrors CampaignGame.format_state_tooltip:
// name + delegates + when it votes, the leader, each candidate's support %,
// and the state's stance on the week's issue.
function stateTooltip(state, name) {
  const st = state.states[name]
  if (!st) return name
  const delegates = st.districts.reduce((a, d) => a + d.population, 0)
  const week = state.config.calendar.find((c) => c[0] === name)?.[1]
  let when = ''
  if (week != null) {
    if (week < state.current_date) when = `  (voted week ${week})`
    else if (week === state.current_date) when = '  (votes this week)'
    else when = `  (votes week ${week}, in ${week - state.current_date})`
  }
  const lines = [`${name} (${delegates} delegates)${when}`]
  const winner = state.past_elections?.[name]
  if (winner != null) lines.push(`Won by: ${seatName(state, winner)}`)
  const pcts = supportPercents(st.support)
  if (pcts.length) {
    const leader = st.support.indexOf(Math.max(...st.support))
    lines.push(`Leader: ${seatName(state, leader + 1)}`)
    pcts.forEach((p, i) => lines.push(`  ${seatName(state, i + 1)}: ${p.toFixed(1)}%`))
  } else {
    lines.push('No polling data yet')
  }
  const iss = state.config.issues?.[state.event_of_week]
  if (iss) {
    const pos = Math.round(st.positions?.[state.event_of_week] ?? 0)
    const label = pos > 0 ? iss.pro : pos < 0 ? iss.con : iss.mid
    const suffix = state.config.issues_mode ? '' : '  (informational; Issues mode off)'
    lines.push(`${name} on ${iss.name}: ${label}${suffix}`)
  }
  return lines.join('\n')
}
// us-atlas states carry properties.name (full state names), which match the
// game's state keys directly. Coordinates are lon/lat, so project with
// Albers-USA (handles the Alaska/Hawaii insets; drops territories off-canvas).
const FC = feature(statesTopo, statesTopo.objects.states)

export default function USMap({ state, selected, onSelect, seatColors, zoomTo }) {
  const path = useMemo(() => geoPath(geoAlbersUsa().fitSize([W, H], FC)), [])

  // Zoom the viewBox to a single state's bounds (with padding) when requested.
  const viewBox = useMemo(() => {
    if (!zoomTo) return `0 0 ${W} ${H}`
    const f = FC.features.find((x) => x.properties.name === zoomTo)
    if (!f) return `0 0 ${W} ${H}`
    const [[x0, y0], [x1, y1]] = path.bounds(f)
    const pad = Math.max((x1 - x0), (y1 - y0)) * 0.15 + 8
    return `${x0 - pad} ${y0 - pad} ${(x1 - x0) + 2 * pad} ${(y1 - y0) + 2 * pad}`
  }, [zoomTo, path])

  function leaderColor(name) {
    const st = state.states[name]
    if (!st) return null
    const p = st.polling_average
    if (!p || !p.length || p.every((x) => x === 0)) return null
    return seatColors[p.indexOf(Math.max(...p))]
  }
  function votesSoon(name) {
    const e = state.config.calendar.find((c) => c[0] === name)
    return e && e[1] >= state.current_date && e[1] <= state.current_date + 1
  }

  return (
    <svg viewBox={viewBox} className="usmap" role="img" aria-label="US map">
      {FC.features.map((f) => {
        const name = f.properties.name
        const d = path(f)
        if (!d) return null
        const inGame = !!state.states[name]
        const isSel = selected === name
        const soon = votesSoon(name)
        // A decided state is colored by its actual winner and dimmed; an
        // undecided one by the current poll leader.
        const winner = state.past_elections?.[name]
        let fill, fillOpacity
        if (winner != null) {
          fill = darken(seatColors[winner - 1] || '#39445c', 0.5)
          fillOpacity = 1
        } else {
          const lc = leaderColor(name)
          fill = lc || (inGame ? '#39445c' : '#222a3a')
          fillOpacity = inGame ? 0.9 : 0.3
        }
        return (
          <path
            key={f.id}
            d={d}
            fill={fill}
            fillOpacity={fillOpacity}
            stroke={isSel ? '#ffffff' : soon ? '#ffb23e' : '#0f1420'}
            strokeWidth={isSel ? 2.2 : soon ? 1.6 : 0.6}
            style={{ cursor: inGame ? 'pointer' : 'default', transition: 'fill .2s' }}
            onClick={() => inGame && onSelect(name)}
          >
            <title>{inGame ? stateTooltip(state, name) : name}</title>
          </path>
        )
      })}
    </svg>
  )
}
