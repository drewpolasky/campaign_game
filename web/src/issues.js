// Human-readable label for a stance on an issue, using the issue's per-side
// labels (from /api/issues or match config.issues).
export function sideLabel(issue, position) {
  const v = Math.round(position || 0)
  if (!issue) return v > 0 ? 'Support' : v < 0 ? 'Oppose' : 'Neutral'
  if (v > 0) return issue.pro
  if (v < 0) return issue.con
  return issue.mid
}

// Ordered choices for a position picker.
export const POSITION_CHOICES = [
  { value: 1, key: 'pro' },
  { value: 0, key: 'mid' },
  { value: -1, key: 'con' },
]
