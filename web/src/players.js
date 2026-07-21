// Shared helpers for player-facing labels.

export function seatName(state, seat) {
  return state.config.seats.find((s) => s.seat === seat)?.name || `Player ${seat}`
}

// Per-seat support as percentages of the total (mirrors the desktop tooltips).
// Returns [] when there's no support yet.
export function supportPercents(support) {
  const total = (support || []).reduce((a, b) => a + b, 0)
  if (!support || !support.length || total <= 0) return []
  return support.map((s) => (100 * s) / total)
}
