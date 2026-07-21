import { useParams } from 'react-router-dom'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api.js'
import USMap from '../USMap.jsx'
import StateDistrictMap from '../StateDistrictMap.jsx'
import { sideLabel } from '../issues.js'

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
  const [selected, setSelected] = useState(null)
  const [districtSel, setDistrictSel] = useState(null)
  const [showHistory, setShowHistory] = useState(false)
  const [showOpponents, setShowOpponents] = useState(false)
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

  const isSpectator = info?.controller === 'spectator'
  const seat = info?.seat
  const idx = seat - 1
  const me = state && seat != null && !isSpectator ? state.players[String(seat)] : null

  // Spectators just watch — poll for the latest state.
  useEffect(() => {
    if (!isSpectator) return
    const iv = setInterval(() => { load().catch(() => {}) }, 5000)
    return () => clearInterval(iv)
  }, [isSpectator])

  // Clear the highlighted district whenever the selected state changes.
  useEffect(() => { setDistrictSel(null) }, [selected])

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
  if (!state || (!me && !isSpectator)) return <div className="wrap"><p className="muted">Loading…</p></div>

  if (isSpectator) return <Spectator state={state} status={status} />

  const iSubmitted = status?.seats?.find((s) => s.seat === seat)?.submitted
  const gameOver = status?.game_over

  if (showHistory) {
    return (
      <div className="wrap wrap-wide">
        <div className="spread">
          <h1>{me.public_name || `Seat ${seat}`} <span className="muted small">· history</span></h1>
          <button className="secondary small" onClick={() => setShowHistory(false)}>← Back to game</button>
        </div>
        <History matchId={info.match_id} token={token} seats={state.config.seats} />
      </div>
    )
  }

  return (
    <div className="wrap wrap-wide">
      <div className="spread">
        <h1>{me.public_name || `Seat ${seat}`}</h1>
        <div className="row">
          <button className="secondary small" onClick={() => setShowOpponents(true)}>👥 Opponents</button>
          <button className="secondary small" onClick={() => setShowHistory(true)}>📜 History</button>
          <span className="pill">Week {state.current_date} / {state.config.num_turns}</span>
        </div>
      </div>

      {showOpponents && <Opponents state={state} mySeat={seat} onClose={() => setShowOpponents(false)} />}

      {state.config.issues_mode && state.config.issues?.[state.event_of_week] && (
        <IssueBanner issue={state.config.issues[state.event_of_week]} me={me} eventIdx={state.event_of_week} />
      )}
      {Object.keys(state.week_results?._state_results || {}).length > 0 && (
        <LastWeek results={state.week_results} seats={state.config.seats} />
      )}

      {gameOver ? (
        <FinalResults state={state} />
      ) : (
        <div className="play-grid">
          {/* LEFT — vote calendar + search (mirrors the desktop sidebar) */}
          <aside className="col-left">
            <CalendarPanel state={state} idx={idx} move={move} selected={selected}
              onSelect={setSelected} setOrg={setOrg} disabled={iSubmitted} />
          </aside>

          {/* CENTER — national map; drills into a state's district map */}
          <main className="col-center">
            <div className="panel">
              {selected ? (
                <>
                  <div className="spread" style={{ marginBottom: 8 }}>
                    <strong>{selected} <span className="muted small">· districts</span></strong>
                    <button className="secondary small" onClick={() => setSelected(null)}>← National map</button>
                  </div>
                  <StateDistrictMap stateName={selected} state={state} idx={idx}
                    seatColors={SEAT_COLORS} selectedDistrict={districtSel} onSelectDistrict={setDistrictSel} />
                  <p className="muted small" style={{ textAlign: 'center', marginTop: 6 }}>
                    Districts colored by current leader · click one to highlight it in the panel →
                  </p>
                </>
              ) : (
                <>
                  <USMap state={state} selected={selected} onSelect={setSelected} seatColors={SEAT_COLORS} />
                  <p className="muted small" style={{ textAlign: 'center', marginTop: 6 }}>
                    Colored by current leader · <span style={{ color: '#ffb23e' }}>orange</span> = votes this/next week · click a state to open its districts
                  </p>
                </>
              )}
            </div>
          </main>

          {/* RIGHT — dashboard + the selected state's districts */}
          <aside className="col-right">
            <Dashboard me={me} timeLeft={timeLeft} moneyLeft={moneyLeft} over={overBudget} />
            {!iSubmitted && (
              <div className="panel">
                <div className="muted small" style={{ marginBottom: 8 }}>Unused time auto-fundraises. Leftover money carries over.</div>
                <button onClick={submit} disabled={busy || overBudget} style={{ width: '100%' }}>
                  {busy ? 'Submitting…' : overBudget ? 'Over budget' : 'End Turn'}
                </button>
              </div>
            )}
            <SeatBar status={status} seat={seat} />
            {iSubmitted ? (
              <div className="panel"><p className="muted">✓ Turn submitted. Waiting for the other players… (auto-refreshing)</p></div>
            ) : selected ? (
              <StateDetail name={selected} state={state} idx={idx} move={move}
                onClose={() => setSelected(null)}
                selectedDistrict={districtSel} onSelectDistrict={setDistrictSel}
                setCampaign={setCampaign} setAd={setAd} setOrg={setOrg} />
            ) : (
              <div className="panel"><p className="muted">Pick a state — from the calendar or the map — to zoom in and campaign, buy ads, and build organization district by district.</p></div>
            )}
          </aside>
        </div>
      )}

      {error && <p className="error">{error}</p>}
    </div>
  )
}

function CalendarPanel({ state, idx, move, selected, onSelect, setOrg, disabled }) {
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState('all')  // all | this | upcoming
  const cur = state.current_date

  const rows = state.config.calendar
    .filter(([name]) => state.states[name])
    .filter(([name]) => name.toLowerCase().includes(q.toLowerCase()))
    .filter(([, week]) => filter === 'all' || (filter === 'this' ? week === cur : week >= cur))

  return (
    <div className="panel col-scroll">
      <h3 style={{ marginBottom: 6 }}>Calendar</h3>
      <input placeholder="Search state…" value={q} onChange={(e) => setQ(e.target.value)}
        style={{ width: '100%', marginBottom: 8 }} />
      <div className="row small" style={{ marginBottom: 8, gap: 10 }}>
        {[['all', 'All'], ['this', 'This week'], ['upcoming', 'Still to vote']].map(([v, l]) => (
          <label key={v} style={{ display: 'flex', gap: 4, alignItems: 'center', cursor: 'pointer', margin: 0 }}>
            <input type="radio" name="calfilter" checked={filter === v} onChange={() => setFilter(v)} />{l}
          </label>
        ))}
      </div>
      <div className="cal-list">
        {rows.map(([name, week]) => {
          const st = state.states[name]
          const org = st.organizations[idx]
          const pending = move.orgs[name] || 0
          const delegates = st.districts.reduce((a, d) => a + d.population, 0)
          const past = week < cur, now = week === cur
          const onBallot = org > 0
          const tier = org + pending
          const cost = tier <= 1 ? 10000 : 10000 * tier
          const canBuild = org > 0 || cur <= week
          const leader = leaderSeat(st)
          return (
            <div key={name}
              className={'cal-row' + (selected === name ? ' sel' : '') + (past ? ' past' : '') + (onBallot ? ' ballot' : '')}
              onClick={() => onSelect(name)}>
              <div className="cal-main">
                {leader && <span className="leader-dot" style={{ background: SEAT_COLORS[leader - 1] }} />}
                {now && <span className="pill warn small" style={{ marginRight: 4 }}>now</span>}
                {onBallot && '★ '}{name}
                <span className="muted small"> · wk {week} · {delegates} del{pending ? ` · +${pending} org` : ''}</span>
              </div>
              {!disabled && !past && canBuild && (
                <button className="secondary small" style={{ whiteSpace: 'nowrap' }}
                  onClick={(e) => { e.stopPropagation(); setOrg(name, pending + 1) }}>
                  {tier === 0 ? 'Ballot $10k' : tier === 1 ? 'Office $10k' : `+$${Math.round(cost / 1000)}k`}
                </button>
              )}
            </div>
          )
        })}
        {rows.length === 0 && <p className="muted small">No states match.</p>}
      </div>
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

function Spectator({ state, status }) {
  const players = Object.entries(state.players)
    .map(([seat, p]) => ({ seat: Number(seat), name: p.public_name, delegates: Math.round(p.delegate_count), momentum: Math.round(p.momentum) }))
    .sort((a, b) => b.delegates - a.delegates)
  const gameOver = status?.game_over
  return (
    <div className="wrap">
      <div className="spread">
        <h1>Spectating</h1>
        <span className="pill">Week {state.current_date} / {state.config.num_turns}{gameOver ? ' · finished' : ''}</span>
      </div>
      <div className="panel">
        <h3>Standings</h3>
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead><tr><th>#</th><th>Candidate</th><th>Delegates</th><th>Momentum</th><th>This turn</th></tr></thead>
            <tbody>
              {players.map((p, i) => {
                const ss = status?.seats?.find((s) => s.seat === p.seat)
                return (
                  <tr key={p.seat}>
                    <td>{i + 1}</td>
                    <td><span className="leader-dot" style={{ background: SEAT_COLORS[p.seat - 1] }} />{p.name}</td>
                    <td>{p.delegates.toLocaleString()}</td>
                    <td>{p.momentum}</td>
                    <td className="muted small">{ss ? (ss.controller === 'human' ? (ss.submitted ? 'submitted' : 'thinking') : 'AI') : ''}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
      <div className="panel">
        <USMap state={state} selected={null} onSelect={() => {}} seatColors={SEAT_COLORS} />
        <p className="muted small" style={{ textAlign: 'center', marginTop: 6 }}>Colored by current leader · auto-refreshing</p>
      </div>
      {Object.keys(state.week_results?._state_results || {}).length > 0 && (
        <LastWeek results={state.week_results} seats={state.config.seats} />
      )}
      {gameOver && <FinalResults state={state} />}
    </div>
  )
}

function Opponents({ state, mySeat, onClose }) {
  const issues = state.config.issues || []
  const showStances = state.config.issues_mode && issues.length > 0
  const opps = Object.entries(state.players)
    .map(([seat, p]) => ({ seat: Number(seat), p }))
    .filter((o) => o.seat !== mySeat)
    .sort((a, b) => a.seat - b.seat)
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="spread">
          <h3 style={{ margin: 0 }}>Opponents{showStances ? "' stances" : ''}</h3>
          <button className="secondary small" onClick={onClose}>Close</button>
        </div>
        <div className="opp-grid">
          {opps.map(({ seat, p }) => (
            <div key={seat} className="panel" style={{ background: 'var(--panel-2)', marginBottom: 0 }}>
              <div className="row" style={{ marginBottom: 2 }}>
                <span className="leader-dot" style={{ background: SEAT_COLORS[seat - 1] }} />
                <strong>{p.public_name || `Player ${seat}`}</strong>
              </div>
              <div className="muted small" style={{ marginBottom: showStances ? 8 : 0 }}>
                Momentum {Math.round(p.momentum)} · Delegates {Math.round(p.delegate_count)}
              </div>
              {showStances && (
                <table><tbody>
                  {issues.map((iss, i) => (
                    <tr key={iss.name}>
                      <td className="muted small">{iss.name}</td>
                      <td className="small">{sideLabel(iss, p.positions?.[i] ?? 0)}</td>
                    </tr>
                  ))}
                </tbody></table>
              )}
            </div>
          ))}
          {opps.length === 0 && <p className="muted">No opponents in this game.</p>}
        </div>
      </div>
    </div>
  )
}

function IssueBanner({ issue, me, eventIdx }) {
  const myPos = me.positions?.[eventIdx] ?? 0
  return (
    <div className="panel" style={{ borderColor: 'var(--accent)' }}>
      <strong>📣 Issue this week: {issue.name}</strong>
      <span className="muted"> · your stance: <b style={{ color: 'var(--text)' }}>{sideLabel(issue, myPos)}</b>. States that share your stance are easier to win support in this week; states that clash are harder.</span>
    </div>
  )
}

function StateDetail({ name, state, idx, move, onClose, setCampaign, setAd, setOrg, selectedDistrict, onSelectDistrict }) {
  const st = state.states[name]
  const myOrg = st.organizations[idx]
  const week = contestWeekOf(state, name)
  const past = week < state.current_date
  const pendingOrg = move.orgs[name] || 0
  const canBuildBallot = myOrg > 0 || week == null || state.current_date <= week

  // Issue alignment for the current week (only in issues mode).
  let align = null
  if (state.config.issues_mode) {
    const issue = state.config.issues?.[state.event_of_week]
    const statePos = Math.round(st.positions?.[state.event_of_week] ?? 0)
    const myPos = Math.round(state.players[String(idx + 1)]?.positions?.[state.event_of_week] ?? 0)
    if (issue) {
      if (statePos === 0) align = { cls: 'muted', text: `${name} is neutral on ${issue.name} this week.` }
      else if (myPos === statePos) align = { cls: 'notice', text: `✓ You align with ${name} on ${issue.name} (${sideLabel(issue, statePos)}) — support is easier here this week.` }
      else align = { cls: 'error', text: `✗ You clash with ${name} on ${issue.name} (they lean ${sideLabel(issue, statePos)}) — support is harder here this week.` }
    }
  }

  // Redistribute the state's currently-allocated time/ads across its districts
  // — evenly, or weighted by each district's delegates — preserving the total
  // (mirrors the desktop Even/Weighted split presets). res honors the input
  // step (1h for time, $1000 for ads).
  function redistribute(kind, weighted) {
    const isTime = kind === 'time'
    const res = isTime ? 1 : 1000
    const alloc = (isTime ? move.campaigning : move.ads)[name] || {}
    const total = Object.values(alloc).reduce((a, b) => a + b, 0)
    const dists = st.districts
    if (total < res || !dists.length) return
    const weights = weighted ? dists.map((d) => d.population) : dists.map(() => 1)
    const wtot = weights.reduce((a, b) => a + b, 0)
    const units = Math.floor(total / res)
    const raw = weights.map((w) => (units * w) / wtot)
    const snapped = raw.map((r) => Math.floor(r))
    const leftover = units - snapped.reduce((a, b) => a + b, 0)
    const order = raw.map((r, i) => [r - snapped[i], i]).sort((a, b) => b[0] - a[0]).map((x) => x[1])
    for (let k = 0; k < leftover; k++) snapped[order[k % order.length]]++
    dists.forEach((d, i) => (isTime ? setCampaign : setAd)(name, d.name, snapped[i] * res))
  }
  function clearState() {
    for (const d of st.districts) { setCampaign(name, d.name, 0); setAd(name, d.name, 0) }
  }

  return (
    <div className="panel">
      <div className="spread">
        <h3 style={{ margin: 0 }}>{name} <span className="muted small">· votes week {week}</span></h3>
        <button className="secondary small" onClick={onClose}>Close</button>
      </div>
      {align && <p className={align.cls + ' small'} style={{ marginTop: 6 }}>{align.text}</p>}
      {past && <p className="muted small">This state has already voted.</p>}
      {!past && (
        <div className="row" style={{ margin: '10px 0' }}>
          <span className="muted small">Organization tier {myOrg}{pendingOrg ? ` → ${myOrg + pendingOrg}` : ''}</span>
          <button className="secondary small" disabled={!canBuildBallot}
            onClick={() => setOrg(name, pendingOrg + 1)}>
            {myOrg + pendingOrg === 0 ? 'Get on ballot' : 'Upgrade org'} (${orgBuildCost(myOrg + pendingOrg, 1).toLocaleString()})
          </button>
          {pendingOrg > 0 && <button className="secondary small" onClick={() => setOrg(name, pendingOrg - 1)}>Undo</button>}
          {!canBuildBallot && <span className="muted small">contest already voted</span>}
        </div>
      )}
      {!past && (
        <div className="row small" style={{ marginBottom: 8, gap: 6 }}>
          <span className="muted">Split what's allocated:</span>
          <button className="secondary small" onClick={() => redistribute('time', false)}>Even time</button>
          <button className="secondary small" onClick={() => redistribute('ads', false)}>Even $</button>
          <button className="secondary small" onClick={() => redistribute('time', true)}>Weighted time</button>
          <button className="secondary small" onClick={() => redistribute('ads', true)}>Weighted $</button>
          <button className="secondary small" onClick={clearState}>Clear</button>
        </div>
      )}
      <table className="dtable">
        <thead><tr><th>District</th><th>Del.</th><th>Support</th>{!past && <><th>Hrs</th><th>Ad $</th></>}</tr></thead>
        <tbody>
          {st.districts.map((d) => (
            <tr key={d.name}
              ref={(el) => { if (el && selectedDistrict === d.name.trim()) el.scrollIntoView({ block: 'nearest' }) }}
              onClick={() => onSelectDistrict?.(d.name.trim())}
              style={{ cursor: 'pointer', background: selectedDistrict === d.name.trim() ? 'rgba(79,140,255,.15)' : undefined }}>
              <td>{d.name}</td>
              <td>{d.population}</td>
              <td>
                {d.support.map((s, i) => (
                  <span key={i} title={state.config.seats.find((x) => x.seat === i + 1)?.name}
                    style={{ color: SEAT_COLORS[i], fontWeight: i === idx ? 700 : 400, marginRight: 8 }}>
                    {Math.round(s)}
                  </span>
                ))}
              </td>
              {!past && (
                <>
                  <td><input type="number" min="0" placeholder="0"
                    value={move.campaigning[name]?.[d.name] || ''}
                    onChange={(e) => setCampaign(name, d.name, Math.max(0, parseInt(e.target.value) || 0))} /></td>
                  <td><input type="number" min="0" step="1000" placeholder="0"
                    value={move.ads[name]?.[d.name] || ''}
                    onChange={(e) => setAd(name, d.name, Math.max(0, parseInt(e.target.value) || 0))} /></td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
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

function summarizeMove(mv) {
  let camp = 0, ads = 0, orgs = 0
  const states = new Set()
  for (const [st, dists] of Object.entries(mv.campaigning || {})) {
    for (const h of Object.values(dists)) camp += h
    if (Object.keys(dists).length) states.add(st)
  }
  for (const [st, dists] of Object.entries(mv.ads || {})) {
    for (const d of Object.values(dists)) ads += d
    if (Object.keys(dists).length) states.add(st)
  }
  for (const [st, n] of Object.entries(mv.orgs || {})) { orgs += n; if (n) states.add(st) }
  return { camp, ads, orgs, states: states.size }
}

function History({ matchId, token, seats }) {
  const [log, setLog] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    api.getLog(matchId, token).then((r) => setLog(r.log)).catch((e) => setErr(e.message))
  }, [matchId, token])
  const nameOf = (s) => seats.find((x) => x.seat === Number(s))?.name || `Seat ${s}`

  if (err) return <p className="error">{err}</p>
  if (!log) return <p className="muted">Loading history…</p>
  if (log.length === 0) return <div className="panel"><p className="muted">No weeks have resolved yet — come back after the first week.</p></div>

  return (
    <>
      {log.slice().reverse().map((entry) => {
        const stateResults = entry.results?._state_results || {}
        return (
          <div key={entry.week} className="panel">
            <h3 style={{ marginBottom: 8 }}>Week {entry.week}</h3>
            {Object.keys(stateResults).length > 0 && (
              <div style={{ overflowX: 'auto' }}>
                <table>
                  <thead><tr><th>Decided state</th><th>Winner</th><th>Vote share</th></tr></thead>
                  <tbody>
                    {Object.entries(stateResults).map(([sname, r]) => (
                      <tr key={sname}>
                        <td>{sname}</td>
                        <td><span className="leader-dot" style={{ background: SEAT_COLORS[r.winner - 1] }} />{nameOf(r.winner)}</td>
                        <td className="muted small">{Object.entries(r.percentages).filter(([, p]) => p > 0).map(([s, p]) => `${nameOf(Number(s))} ${p}%`).join(' · ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div style={{ overflowX: 'auto', marginTop: Object.keys(stateResults).length ? 10 : 0 }}>
              <table>
                <thead><tr><th>Candidate</th><th>Campaign hrs</th><th>Ad $</th><th>Orgs</th><th>States active</th></tr></thead>
                <tbody>
                  {Object.entries(entry.moves).sort((a, b) => Number(a[0]) - Number(b[0])).map(([seat, mv]) => {
                    const s = summarizeMove(mv)
                    return (
                      <tr key={seat}>
                        <td><span className="leader-dot" style={{ background: SEAT_COLORS[Number(seat) - 1] }} />{nameOf(seat)}</td>
                        <td>{s.camp}</td>
                        <td>${s.ads.toLocaleString()}</td>
                        <td>{s.orgs}</td>
                        <td>{s.states}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )
      })}
    </>
  )
}

function FinalResults({ state }) {
  const players = Object.entries(state.players)
    .map(([seat, p]) => {
      const st = p.stats || {}
      const sup = (st.support_from_org || 0) + (st.support_from_campaign || 0) + (st.support_from_ads || 0)
      return {
        seat: Number(seat), name: p.public_name,
        delegates: Math.round(p.delegate_count),
        statesWon: (st.states_won || []).length,
        districtsWon: st.districts_won || 0,
        org: st.support_from_org || 0, camp: st.support_from_campaign || 0, ads: st.support_from_ads || 0, sup,
      }
    })
    .sort((a, b) => b.delegates - a.delegates)
  const winner = players[0]
  const pct = (v, total) => (total > 0 ? Math.round((v / total) * 100) : 0)
  return (
    <>
      <div className="panel" style={{ textAlign: 'center', borderColor: SEAT_COLORS[winner.seat - 1] }}>
        <h2 style={{ margin: 0 }}>🏆 {winner.name} wins the nomination</h2>
        <p className="muted">{winner.delegates.toLocaleString()} delegates · {winner.statesWon} states carried</p>
      </div>
      <div className="panel">
        <h3>Final standings</h3>
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead><tr><th>#</th><th>Candidate</th><th>Delegates</th><th>States</th><th>Districts</th><th>Support mix (org / campaign / ads)</th></tr></thead>
            <tbody>
              {players.map((p, i) => (
                <tr key={p.seat}>
                  <td>{i + 1}</td>
                  <td><span className="leader-dot" style={{ background: SEAT_COLORS[p.seat - 1] }} />{p.name}{i === 0 ? ' 🏆' : ''}</td>
                  <td>{p.delegates.toLocaleString()}</td>
                  <td>{p.statesWon}</td>
                  <td>{p.districtsWon}</td>
                  <td className="muted small">{pct(p.org, p.sup)}% / {pct(p.camp, p.sup)}% / {pct(p.ads, p.sup)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
