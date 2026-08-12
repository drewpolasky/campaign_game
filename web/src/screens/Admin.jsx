import { useState } from 'react'
import { api } from '../api.js'

// Compact one-line-per-state summary of a seat's move for the log view.
function summarizeMove(move) {
  if (!move) return ['(no move recorded)']
  const lines = []
  const states = new Set([
    ...Object.keys(move.campaigning || {}),
    ...Object.keys(move.ads || {}),
    ...Object.keys(move.orgs || {}),
  ])
  for (const s of [...states].sort()) {
    const parts = []
    const camp = move.campaigning?.[s]
    if (camp) {
      const hours = Object.values(camp).reduce((a, b) => a + b, 0)
      if (hours > 0) parts.push(`${hours}h campaigning`)
    }
    const ads = move.ads?.[s]
    if (ads) {
      const dollars = Object.values(ads).reduce((a, b) => a + b, 0)
      if (dollars > 0) parts.push(`$${dollars.toLocaleString()} ads`)
    }
    const orgs = move.orgs?.[s]
    if (orgs) parts.push(`+${orgs} org`)
    if (parts.length) lines.push(`${s}: ${parts.join(', ')}`)
  }
  return lines.length ? lines : ['(passed — no allocations)']
}

function WeekLog({ entry, standings }) {
  const results = entry.results || {}
  const stateResults = results._state_results || {}
  const seatName = (seat) => standings?.[seat]?.name || `Seat ${seat}`
  const seatKeys = Object.keys(entry.moves || {}).sort((a, b) => Number(a) - Number(b))
  return (
    <div className="panel" style={{ marginTop: 8 }}>
      <h4 style={{ margin: '4px 0' }}>Week {entry.week}</h4>
      {Object.keys(stateResults).length > 0 && (
        <p className="muted small" style={{ margin: '4px 0' }}>
          Decided: {Object.entries(stateResults).map(([st, r]) =>
            `${st} → ${seatName(r.winner)}`).join('; ')}
        </p>
      )}
      {seatKeys.map((seat) => (
        <div key={seat} style={{ marginBottom: 6 }}>
          <b>{seatName(seat)}</b>
          {results[seat]?.delegates > 0 && (
            <span className="muted small"> (+{results[seat].delegates} delegates)</span>
          )}
          <div className="muted small" style={{ whiteSpace: 'pre-line', marginLeft: 12 }}>
            {summarizeMove(entry.moves[seat]).join('\n')}
          </div>
        </div>
      ))}
    </div>
  )
}

// A seat's magic link: opens in a new tab, or copies the full URL. Kept short
// on screen since the token itself is long and unguessable.
function SeatLink({ path }) {
  const url = window.location.origin + path
  const [copied, setCopied] = useState(false)
  return (
    <>
      <a href={path} target="_blank" rel="noreferrer">open</a>
      {' · '}
      <a href="#" onClick={(e) => {
        e.preventDefault()
        navigator.clipboard.writeText(url).then(() => {
          setCopied(true); setTimeout(() => setCopied(false), 1200)
        })
      }}>{copied ? 'copied!' : 'copy link'}</a>
    </>
  )
}

function MatchRow({ m, adminKey, onKilled }) {
  const [log, setLog] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function toggleLog() {
    if (log) { setLog(null); return }
    setBusy(true); setError('')
    try { setLog(await api.adminMatchLog(m.id, adminKey)) }
    catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  async function kill() {
    if (!window.confirm(`Kill match ${m.id}? This deletes the game and its history permanently; every seat link stops working.`)) return
    setBusy(true); setError('')
    try { await api.adminKillMatch(m.id, adminKey); onKilled() }
    catch (e) { setError(e.message); setBusy(false) }
  }

  const created = m.created ? new Date(m.created * 1000).toLocaleString() : ''
  return (
    <>
      <tr>
        <td className="mono">{m.id}</td>
        <td>{m.status}{m.status === 'active' && m.waiting_on?.length > 0 &&
          <span className="muted small"> (waiting on {m.waiting_on.join(', ')})</span>}</td>
        <td>{m.current_week}{m.num_turns ? ` / ${m.num_turns}` : ''}</td>
        <td className="small">
          {m.seats.map((s) => (
            <div key={s.seat} style={{ whiteSpace: 'nowrap' }}>
              {s.name}{' '}
              {s.play_path ? <SeatLink path={s.play_path} /> : <span className="muted">(AI)</span>}
            </div>
          ))}
          {m.spectator_path && (
            <div style={{ whiteSpace: 'nowrap', marginTop: 2 }}>
              <span className="muted">spectator</span> <SeatLink path={m.spectator_path} />
            </div>
          )}
        </td>
        <td className="muted small">{created}</td>
        <td>
          <div className="row">
            <button className="secondary small" onClick={toggleLog} disabled={busy}>
              {log ? 'Hide log' : 'View log'}
            </button>
            <button className="small" onClick={kill} disabled={busy}
              style={{ background: '#b03030' }}>Kill</button>
          </div>
        </td>
      </tr>
      {(log || error) && (
        <tr>
          <td colSpan={6}>
            {error && <p className="error">{error}</p>}
            {log && (
              <div>
                <p className="muted small" style={{ margin: '4px 0' }}>
                  Standings: {Object.entries(log.standings || {})
                    .sort((a, b) => Number(a[0]) - Number(b[0]))
                    .map(([seat, p]) => `${p.name}: ${Math.round(p.delegates)} del, $${Math.round(p.money).toLocaleString()}`)
                    .join('  ·  ')}
                  {log.pending_submissions?.length > 0 &&
                    ` — submitted this week: ${log.pending_submissions.join(', ')}`}
                </p>
                {(log.log || []).length === 0
                  ? <p className="muted small">No weeks resolved yet.</p>
                  : log.log.map((entry) => (
                      <WeekLog key={entry.week} entry={entry} standings={log.standings} />
                    ))}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

export default function Admin() {
  const [key, setKey] = useState(() => sessionStorage.getItem('campaign_admin_key') || '')
  const [entered, setEntered] = useState('')
  const [matches, setMatches] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function load(adminKey) {
    setBusy(true); setError('')
    try {
      const res = await api.adminListMatches(adminKey)
      setMatches(res.matches)
      sessionStorage.setItem('campaign_admin_key', adminKey)
      setKey(adminKey)
    } catch (e) {
      setError(e.message)
      setMatches(null)
    } finally { setBusy(false) }
  }

  if (!matches) {
    return (
      <div className="wrap">
        <h1>Admin</h1>
        <div className="panel" style={{ maxWidth: 420 }}>
          <label>Admin password</label>
          <input type="password" value={entered} autoFocus
            onChange={(e) => setEntered(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') load(entered || key) }} />
          <div className="row" style={{ marginTop: 10 }}>
            <button onClick={() => load(entered || key)} disabled={busy}>
              {busy ? 'Checking…' : 'Enter'}
            </button>
          </div>
          {error && <p className="error" style={{ marginTop: 10 }}>{error}</p>}
        </div>
      </div>
    )
  }

  return (
    <div className="wrap">
      <h1>Admin — matches</h1>
      <div className="row" style={{ marginBottom: 10 }}>
        <button className="secondary" onClick={() => load(key)} disabled={busy}>Refresh</button>
        <span className="muted small">{matches.length} match{matches.length === 1 ? '' : 'es'}</span>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="panel">
        <table>
          <thead>
            <tr><th>ID</th><th>Status</th><th>Week</th><th>Seats</th><th>Created</th><th></th></tr>
          </thead>
          <tbody>
            {matches.map((m) => (
              <MatchRow key={m.id} m={m} adminKey={key} onKilled={() => load(key)} />
            ))}
          </tbody>
        </table>
        {matches.length === 0 && <p className="muted">No matches on the server.</p>}
      </div>
    </div>
  )
}
