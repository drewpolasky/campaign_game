import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { POSITION_CHOICES } from '../issues.js'

const AI_STRATEGIES = ['Default', 'Aggressive', 'BigState', 'CloseOnly', 'MoneyMachine', 'Balanced']
const TURN_OPTIONS = [8, 10, 20]

function blankSeat(n, controller = 'human') {
  return { name: `Candidate ${n}`, controller, ai_strategy: 'Default', positions: [] }
}

export default function Lobby() {
  const [numTurns, setNumTurns] = useState(10)
  const [issuesMode, setIssuesMode] = useState(false)
  const [seats, setSeats] = useState([blankSeat(1, 'human'), blankSeat(2, 'ai')])
  const [issues, setIssues] = useState([])
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.getIssues().then(setIssues).catch(() => {}) }, [])

  function setPos(i, issueIdx, val) {
    setSeats(seats.map((s, j) => {
      if (j !== i) return s
      const positions = issues.map((_, k) => (k === issueIdx ? val : (s.positions?.[k] ?? 0)))
      return { ...s, positions }
    }))
  }

  const randomStance = () => issues.map(() => [-1, 0, 1][Math.floor(Math.random() * 3)])
  function randomizeSeat(i) {
    setSeats(seats.map((s, j) => (j === i ? { ...s, positions: randomStance() } : s)))
  }
  function randomizeAll() {
    setSeats(seats.map((s) => (s.controller === 'human' ? { ...s, positions: randomStance() } : s)))
  }

  function setSeat(i, patch) {
    setSeats(seats.map((s, j) => (j === i ? { ...s, ...patch } : s)))
  }
  function addSeat() {
    if (seats.length >= 10) return
    setSeats([...seats, blankSeat(seats.length + 1, 'ai')])
  }
  function removeSeat(i) {
    if (seats.length <= 2) return
    setSeats(seats.filter((_, j) => j !== i))
  }

  async function create() {
    setBusy(true); setError('')
    try {
      const config = {
        num_turns: numTurns,
        issues_mode: issuesMode,
        seats: seats.map((s) => ({
          name: s.name,
          controller: s.controller,
          ai_strategy: s.controller === 'ai' ? s.ai_strategy : null,
          // Human platforms only matter in issues mode; AI seats get randomized
          // positions server-side, so send null for them.
          positions: (s.controller === 'human' && issuesMode)
            ? issues.map((_, k) => s.positions?.[k] ?? 0)
            : null,
        })),
      }
      setResult(await api.createMatch(config))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const origin = window.location.origin

  return (
    <div className="wrap">
      <h1>New Campaign</h1>
      <p className="muted">Set up a match, then share each player's private link.</p>

      {!result && (
        <div className="panel">
          <div className="row" style={{ marginBottom: 16 }}>
            <div>
              <label>Weeks</label>
              <select value={numTurns} onChange={(e) => setNumTurns(Number(e.target.value))}>
                {TURN_OPTIONS.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label>Issues mode</label>
              <select value={issuesMode ? 'on' : 'off'} onChange={(e) => setIssuesMode(e.target.value === 'on')}>
                <option value="off">Off</option>
                <option value="on">On</option>
              </select>
            </div>
          </div>

          <table>
            <thead>
              <tr><th>Seat</th><th>Name</th><th>Controller</th><th>AI strategy</th><th></th></tr>
            </thead>
            <tbody>
              {seats.map((s, i) => (
                <tr key={i}>
                  <td>{i + 1}</td>
                  <td><input value={s.name} onChange={(e) => setSeat(i, { name: e.target.value })} /></td>
                  <td>
                    <select value={s.controller} onChange={(e) => setSeat(i, { controller: e.target.value })}>
                      <option value="human">Human</option>
                      <option value="ai">AI</option>
                    </select>
                  </td>
                  <td>
                    {s.controller === 'ai' ? (
                      <select value={s.ai_strategy} onChange={(e) => setSeat(i, { ai_strategy: e.target.value })}>
                        {AI_STRATEGIES.map((a) => <option key={a} value={a}>{a}</option>)}
                      </select>
                    ) : <span className="muted small">—</span>}
                  </td>
                  <td>
                    <button className="secondary" onClick={() => removeSeat(i)} disabled={seats.length <= 2}>✕</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {issuesMode && issues.length > 0 && (
            <div style={{ marginTop: 18 }}>
              <div className="spread" style={{ marginBottom: 4 }}>
                <h3 style={{ margin: 0 }}>Platforms</h3>
                <button className="secondary small" onClick={randomizeAll}>🎲 Randomize all</button>
              </div>
              <p className="muted small">Each human candidate's stance per issue. Matching a state's stance on the week's issue boosts your support there; clashing hurts. AI candidates get randomized platforms.</p>
              {seats.map((s, i) => s.controller === 'human' && (
                <div key={i} className="panel" style={{ background: 'var(--panel-2)', marginBottom: 8 }}>
                  <div className="spread">
                    <strong>{s.name}</strong>
                    <button className="secondary small" onClick={() => randomizeSeat(i)}>🎲 Randomize</button>
                  </div>
                  <div style={{ overflowX: 'auto' }}>
                    <table>
                      <thead><tr>{issues.map((iss) => <th key={iss.name}>{iss.name}</th>)}</tr></thead>
                      <tbody>
                        <tr>
                          {issues.map((iss, k) => (
                            <td key={iss.name}>
                              <select value={s.positions?.[k] ?? 0} onChange={(e) => setPos(i, k, Number(e.target.value))}>
                                {POSITION_CHOICES.map((c) => <option key={c.value} value={c.value}>{iss[c.key]}</option>)}
                              </select>
                            </td>
                          ))}
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="row" style={{ marginTop: 14 }}>
            <button className="secondary" onClick={addSeat} disabled={seats.length >= 10}>+ Add seat</button>
            <button onClick={create} disabled={busy}>{busy ? 'Creating…' : 'Create match'}</button>
          </div>
          {error && <p className="error" style={{ marginTop: 12 }}>{error}</p>}
        </div>
      )}

      {result && (
        <div className="panel">
          <h2>Match <span className="mono">{result.match_id}</span> created</h2>
          <p className="muted">Send each human player their private link. Anyone with the link plays that seat — no login.</p>
          <table>
            <thead><tr><th>Seat</th><th>Name</th><th>Type</th><th>Link</th></tr></thead>
            <tbody>
              {result.seats.map((s) => {
                const link = result.seat_links[String(s.seat)]
                return (
                  <tr key={s.seat}>
                    <td>{s.seat}</td>
                    <td>{s.name}</td>
                    <td>{s.controller === 'human' ? 'Human' : `AI (${s.ai_strategy})`}</td>
                    <td>
                      {link ? (
                        <div className="row">
                          <a href={link}>{origin}{link}</a>
                          <button className="secondary small" onClick={() => navigator.clipboard.writeText(origin + link)}>Copy</button>
                        </div>
                      ) : <span className="muted small">server-controlled</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {result.spectator_link && (
            <div className="row" style={{ marginTop: 12 }}>
              <span className="muted small">Spectator link (read-only):</span>
              <a href={result.spectator_link}>{origin}{result.spectator_link}</a>
              <button className="secondary small" onClick={() => navigator.clipboard.writeText(origin + result.spectator_link)}>Copy</button>
            </div>
          )}

          <div className="row" style={{ marginTop: 14 }}>
            <button className="secondary" onClick={() => setResult(null)}>Create another</button>
          </div>
        </div>
      )}
    </div>
  )
}
