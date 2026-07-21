import { useParams } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

// Minimal Play screen — proves the loop end to end (resolve token -> load
// state -> submit a turn -> poll -> next week). The full allocation UI
// (district campaigning/ads, org buys, reports) is built on top of this.
export default function Play() {
  const { token } = useParams()
  const [info, setInfo] = useState(null)      // {match_id, seat}
  const [state, setState] = useState(null)    // full match doc
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const pollRef = useRef(null)

  async function load(who) {
    who = who || info
    const s = await api.getState(who.match_id, token)
    setState(s.state)
    setStatus(s.status)
    setError('')
  }

  useEffect(() => {
    (async () => {
      try {
        const who = await api.resolveToken(token)
        setInfo(who)
        await load(who)
      } catch (e) { setError(e.message) }
    })()
    return () => pollRef.current && clearInterval(pollRef.current)
  }, [token])

  async function endTurn() {
    if (!info) return
    setBusy(true); setError('')
    try {
      const res = await api.submitMove(info.match_id, token, {})  // empty move for now
      setStatus(res.status)
      if (res.result === 'resolved') {
        await load()
      } else {
        startPolling()
      }
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  function startPolling() {
    if (pollRef.current) clearInterval(pollRef.current)
    const startWeek = status?.current_week
    pollRef.current = setInterval(async () => {
      try {
        const st = await api.status(info.match_id, token)
        setStatus(st)
        if (st.current_week !== startWeek || st.game_over) {
          clearInterval(pollRef.current); pollRef.current = null
          await load()
        }
      } catch (e) { /* keep polling */ }
    }, 3000)
  }

  if (error) return <div className="wrap"><p className="error">{error}</p></div>
  if (!state || !info) return <div className="wrap"><p className="muted">Loading…</p></div>

  const seat = info.seat
  const me = state.players[String(seat)]
  const iSubmitted = status?.seats?.find((s) => s.seat === seat)?.submitted
  const gameOver = status?.game_over

  return (
    <div className="wrap">
      <div className="spread">
        <h1>{me.public_name || `Seat ${seat}`}</h1>
        <span className="pill">Week {state.current_date} / {state.config.num_turns}</span>
      </div>

      <div className="panel">
        <div className="budget">
          <div><label>Time</label><div className="val">{me.resources[0]}h</div></div>
          <div><label>Money</label><div className="val">${me.resources[1].toLocaleString()}</div></div>
          <div><label>Delegates</label><div className="val">{Math.round(me.delegate_count)}</div></div>
          <div><label>Momentum</label><div className="val">{Math.round(me.momentum)}</div></div>
        </div>
      </div>

      <div className="panel">
        <h3>Seats</h3>
        <table>
          <thead><tr><th>Seat</th><th>Name</th><th>Type</th><th>Status</th></tr></thead>
          <tbody>
            {status?.seats?.map((s) => (
              <tr key={s.seat}>
                <td>{s.seat}{s.seat === seat ? ' (you)' : ''}</td>
                <td>{s.name}</td>
                <td>{s.controller}</td>
                <td>{s.controller === 'human' ? (s.submitted ? <span className="pill good">submitted</span> : <span className="pill warn">thinking</span>) : <span className="muted small">auto</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {gameOver ? (
        <div className="panel"><h2>Game over</h2><p className="notice">Final delegates: {Math.round(me.delegate_count)}</p></div>
      ) : iSubmitted ? (
        <div className="panel"><p className="muted">Waiting for the other players… (auto-refreshing)</p></div>
      ) : (
        <div className="panel">
          <p className="muted">Allocation UI coming next. For now, end your week with no moves.</p>
          <button onClick={endTurn} disabled={busy}>{busy ? 'Submitting…' : 'End Turn'}</button>
        </div>
      )}

      {error && <p className="error">{error}</p>}
    </div>
  )
}
