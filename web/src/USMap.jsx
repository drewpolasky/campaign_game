import { useMemo } from 'react'
import { feature } from 'topojson-client'
import { geoAlbersUsa, geoPath } from 'd3-geo'
import statesTopo from 'us-atlas/states-10m.json'

const W = 960, H = 600
// us-atlas states carry properties.name (full state names), which match the
// game's state keys directly. Coordinates are lon/lat, so project with
// Albers-USA (handles the Alaska/Hawaii insets; drops territories off-canvas).
const FC = feature(statesTopo, statesTopo.objects.states)

export default function USMap({ state, selected, onSelect, seatColors }) {
  const path = useMemo(() => geoPath(geoAlbersUsa().fitSize([W, H], FC)), [])

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
    <svg viewBox={`0 0 ${W} ${H}`} className="usmap" role="img" aria-label="US map">
      {FC.features.map((f) => {
        const name = f.properties.name
        const d = path(f)
        if (!d) return null
        const inGame = !!state.states[name]
        const fill = leaderColor(name)
        const isSel = selected === name
        const soon = votesSoon(name)
        return (
          <path
            key={f.id}
            d={d}
            fill={fill || (inGame ? '#39445c' : '#222a3a')}
            fillOpacity={inGame ? 0.9 : 0.3}
            stroke={isSel ? '#ffffff' : soon ? '#ffb23e' : '#0f1420'}
            strokeWidth={isSel ? 2.2 : soon ? 1.6 : 0.6}
            style={{ cursor: inGame ? 'pointer' : 'default', transition: 'fill .2s' }}
            onClick={() => inGame && onSelect(name)}
          >
            <title>{name}{votesSoon(name) ? ' — votes soon' : ''}</title>
          </path>
        )
      })}
    </svg>
  )
}
