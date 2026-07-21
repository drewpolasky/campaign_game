import { useParams } from 'react-router-dom'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api.js'

const WEEKLY_TIME = 80
const SEAT_COLORS = ['#ff5b5b', '#4f8cff', '#3ecf8e', '#b07bff', '#ffb23e', '#38d6d6',
  '#ff8fce', '#a0d24a', '#d98b4a', '#8a94ff']

// Cost to build `count` org tiers from `fromTier` — mirrors game_service.org_build_cost.
function orgBuildCost(fromTier, count) {
  let total = 0, tier = fromTier
  for (let i = 0; i < count; i++) { total += tier <= 1 ? 10000 : 10000 * tier; tier++ }
  return total
}

function contestWeekOf(state, name) {
  const e = state.config.calendar.find((c) => c[0] === name)
  return e ? e[1] : null
}

function leaderSeat(stateObj) {
  const p = stateObj.polling_average
  if (!p || !p.length || p.every((x) => x === 0)) return null
  return p.indexOf(Math.max(...p)) + 1
}

export default function Play() {
  const { token } = useParams()
  const [info, setInfo] = useState(null)
  const [state, setState] = useState(null)
  const [status, setStatus] = useState(null)
  const [move, setMove] = useState({ campaigning: {}, ads: {}, orgs: {} })
  const [expanded, setExpanded] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const pollRef = useRef(null)

  async function load(who) {
    who = who || info
    const s = await api.getState(who.match_id, token)
    setState(s.state)
    setStatus(s.status)
    setMove({ campaigning: {}, ads: {}, orgs: {} })
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

  const seat = info?.seat
  const idx = seat - 1
  const me = state && seat != null ? state.players[String(seat)] : null

  // Budget math for the pending move.
  const totals = useMemo(() => {
    if (!state) return { time: 0, money: 0 }
    let time = 0, money = 0
    for (const dists of Object.values(move.campaigning)) for (const h of Object.values(dists)) time += h
    for (const dists of Object.values(move.ads)) for (const d of Object.values(dists)) money += d
    for (const [sname, count] of Object.entries(move.orgs)) {
      if (!count) continue
      money += orgBuildCost(state.states[sname].organizations[idx], count)
    }
    return { time, money }
  }, [move, state, idx])

  const timeLeft = WEEKLY_TIME - totals.time
  const moneyLeft = me ? me.resources[1] - totals.money : 0
  const overBudget = timeLeft < 0 || moneyLeft < 0

  function setCampaign(sname, dname, hours) {
    setMove((m) => {
      const c = { ...m.campaigning, [sname]: { ...(m.campaigning[sname] || {}) } }
      if (hours > 0) c[sname][dname] = hours; else delete c[sname][dname]
      if (Object.keys(c[sname]).length === 0) delete c[sname]
      return { ...m, campaigning: c }
    })
  }
  function setAd(sname, dname, dollars) {
    setMove((m) => {
      const a = { ...m.ads, [sname]: { ...(m.ads[sname] || {}) } }
      if (dollars > 0) a[sname][dname] = dollars; else delete a[sname][dname]
      if (Object.keys(a[sname]).length === 0) delete a[sname]
      return { ...m, ads: a }
    })
  }
  function setOrg(sname, count) {
    setMove((m) => {
      const o = { ...m.orgs }
      if (count > 0) o[sname] = count; else delete o[sname]
      return { ...m, orgs: o }
    })
  }

  async function submit() {
    if (!info || overBudget) return
    setBusy(true); setError('')
    try {
      const res = await api.submitMove(info.match_id, token, move)
      setStatus(res.status)
      if (res.result === 'resolved') await load()
      else startPolling()
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
      } catch { /* keep polling */ }
    }, 3000)
  }

  if (error && !state) return <div className="wrap"><p className="error">{error}</p></div>
  if (!state || !me) return <div className="wrap"><p className="muted">Loading…</p></div>

  const iSubmitted = status?.seats?.find((s) => s.seat === seat)?.submitted
  const gameOver = status?.game_over

  // Group states by contest week: upcoming first (soonest first), then past.
  const groups = {}
  for (const name of Object.keys(state.states)) {
    const w = contestWeekOf(state, name)
    ;(groups[w] ??= []).push(name)
  }
  const weeks = Object.keys(groups).map(Number).sort((a, b) => a - b)
  const upcoming = weeks.filter((w) => w >= state.current_date)
  const past = weeks.filter((w) => w < state.current_date)

  return (
    <div className="wrap">
      <div className="spread">
        <h1>{me.public_name || `Seat ${seat}`}</h1>
        <span className="pill">Week {state.current_date} / {state.config.num_turns}</span>
      </div>

      <Dashboard me={me} timeLeft={timeLeft} moneyLeft={moneyLeft} over={overBudget} />

      <SeatBar status={status} seat={seat} />

      {state.week_results && Object.keys(state.week_results._state_results || {}).length > 0 && (
        <LastWeek results={state.week_results} seats={state.config.seats} />
      )}

      {gameOver ? (
        <FinalResults state={state} />
      ) : iSubmitted ? (
        <div className="panel"><p className="muted">✓ Turn submitted. Waiting for the other players… (auto-refreshing every few seconds)</p></div>
      ) : (
        <>
          <div className="panel spread" style={{ position: 'sticky', top: 0, zIndex: 5 }}>
            <div className="muted small">Unused time auto-fundraises. Money left over carries to next week.</div>
            <button onClick={submit} disabled={busy || overBudget}>
              {busy ? 'Submitting…' : overBudget ? 'Over budget' : 'End Turn'}
            </button>
          </div>

          {upcoming.map((w) => (
            <div key={w}>
              <div className="week-header">{w === state.current_date ? 'Voting this week' : `Votes week ${w}`}</div>
              {groups[w].sort().map((name) => (
                <StateCard key={name} name={name} state={state} idx={idx}
                  move={move} expanded={expanded === name}
                  onToggle={() => setExpanded(expanded === name ? null : name)}
                  setCampaign={setCampaign} setAd={setAd} setOrg={setOrg} />
              ))}
            </div>
          ))}

          {past.length > 0 && (
            <>
              <div className="week-header">Already voted</div>
              {past.map((w) => groups[w].sort().map((name) => (
                <StateCard key={name} name={name} state={state} idx={idx}
                  move={move} expanded={expanded === name} past
                  onToggle={() => setExpanded(expanded === name ? null : name)}
                  setCampaign={setCampaign} setAd={setAd} setOrg={setOrg} />
              )))}
            </>
          )}
        </>
      )}

      {error && <p className="error">{error}</p>}
    </div>
  )
}

function Dashboard({ me, timeLeft, moneyLeft, over }) {
  return (
    <div className="panel">
      <div className="budget">
        <div><label>Time left</label><div className={'val' + (timeLeft < 0 ? ' over' : '')}>{timeLeft}h</div></div>
        <div><label>Money left</label><div className={'val' + (moneyLeft < 0 ? ' over' : '')}>${moneyLeft.toLocaleString()}</div></div>
        <div><label>Delegates</label><div className="val">{Math.round(me.delegate_count)}</div></div>
        <div><label>Momentum</label><div className="val">{Math.round(me.momentum)}</div></div>
      </div>
      {over && <p className="error small" style={{ marginTop: 10 }}>You've allocated more than you have — reduce something to end your turn.</p>}
    </div>
  )
}

function SeatBar({ status, seat }) {
  if (!status?.seats) return null
  return (
    <div className="panel">
      <div className="row">
        {status.seats.map((s) => (
          <span key={s.seat} className="pill" style={{ borderColor: SEAT_COLORS[s.seat - 1] }}>
            <span className="leader-dot" style={{ background: SEAT_COLORS[s.seat - 1] }} />
            {s.name}{s.seat === seat ? ' (you)' : ''} · {s.controller === 'human' ? (s.submitted ? 'submitted' : 'thinking') : 'AI'}
          </span>
        ))}
      </div>
    </div>
  )
}

function StateCard({ name, state, idx, move, expanded, past, onToggle, setCampaign, setAd, setOrg }) {
  const st = state.states[name]
  const myOrg = st.organizations[idx]
  const mySupport = st.districts.reduce((a, d) => a + (d.support[idx] || 0), 0)
  const leader = leaderSeat(st)
  const week = contestWeekOf(state, name)
  const pendingOrg = move.orgs[name] || 0
  const canBuildBallot = myOrg > 0 || week == null || state.current_date <= week

  return (
    <div className="state-card" style={{ opacity: past ? 0.6 : 1 }}>
      <div className="head" onClick={onToggle}>
        <div>
          {leader && <span className="leader-dot" style={{ background: SEAT_COLORS[leader - 1] }} />}
          <strong>{name}</strong>
          <span className="muted small"> · week {week} · your org {myOrg}{pendingOrg ? `(+${pendingOrg})` : ''} · your support {Math.round(mySupport)}</span>
        </div>
        <span className="muted">{expanded ? '▾' : '▸'}</span>
      </div>
      {expanded && (
        <div className="body">
          {!past && (
            <div className="row" style={{ marginBottom: 10 }}>
              <span className="muted small">Organization tier {myOrg}{pendingOrg ? ` → ${myOrg + pendingOrg}` : ''}</span>
              <button className="secondary small" disabled={!canBuildBallot}
                onClick={() => setOrg(name, pendingOrg + 1)}>
                {myOrg + pendingOrg === 0 ? 'Get on ballot' : 'Upgrade org'} (${orgBuildCost(myOrg + pendingOrg, 1).toLocaleString()})
              </button>
              {pendingOrg > 0 && <button className="secondary small" onClick={() => setOrg(name, pendingOrg - 1)}>Undo</button>}
              {!canBuildBallot && <span className="muted small">contest already voted</span>}
            </div>
          )}
          <table>
            <thead><tr><th>District</th><th>Your support</th>{!past && <><th>Campaign hrs</th><th>Ad $</th></>}</tr></thead>
            <tbody>
              {st.districts.map((d) => (
                <tr key={d.name}>
                  <td>{d.name}</td>
                  <td>{Math.round(d.support[idx] || 0)}</td>
                  {!past && (
                    <>
                      <td>
                        <input type="number" min="0" value={move.campaigning[name]?.[d.name] || ''}
                          placeholder="0" style={{ width: 70 }}
                          onChange={(e) => setCampaign(name, d.name, Math.max(0, parseInt(e.target.value) || 0))} />
                      </td>
                      <td>
                        <input type="number" min="0" step="1000" value={move.ads[name]?.[d.name] || ''}
                          placeholder="0" style={{ width: 90 }}
                          onChange={(e) => setAd(name, d.name, Math.max(0, parseInt(e.target.value) || 0))} />
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function LastWeek({ results, seats }) {
  const nameOf = (s) => seats.find((x) => x.seat === s)?.name || `Seat ${s}`
  const stateResults = results._state_results || {}
  return (
    <div className="panel">
      <h3>Last week's results</h3>
      <table>
        <thead><tr><th>State</th><th>Winner</th><th>Vote share</th></tr></thead>
        <tbody>
          {Object.entries(stateResults).map(([sname, r]) => (
            <tr key={sname}>
              <td>{sname}</td>
              <td><span className="leader-dot" style={{ background: SEAT_COLORS[r.winner - 1] }} />{nameOf(r.winner)}</td>
              <td className="muted small">
                {Object.entries(r.percentages).filter(([, p]) => p > 0)
                  .map(([s, p]) => `${nameOf(Number(s))} ${p}%`).join(' · ')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FinalResults({ state }) {
  const players = Object.entries(state.players)
    .map(([seat, p]) => ({ seat: Number(seat), name: p.public_name, delegates: Math.round(p.delegate_count) }))
    .sort((a, b) => b.delegates - a.delegates)
  return (
    <div className="panel">
      <h2>Final results</h2>
      <table>
        <thead><tr><th>#</th><th>Candidate</th><th>Delegates</th></tr></thead>
        <tbody>
          {players.map((p, i) => (
            <tr key={p.seat}>
              <td>{i + 1}</td>
              <td><span className="leader-dot" style={{ background: SEAT_COLORS[p.seat - 1] }} />{p.name}{i === 0 ? ' 🏆' : ''}</td>
              <td>{p.delegates}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
