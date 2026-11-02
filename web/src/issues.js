// Human-readable label for a stance on an issue, using the issue's per-side
// labels (from /api/issues or match config.issues).
export function sideLabel(issue, position) {
  const v = Math.round(position || 0)
  if (!issue) return v > 0 ? 'Support' : v < 0 ? 'Oppose' : 'Neutral'
  if (v > 0) return issue.pro
  if (v < 0) return issue.con
  return issue.mid
}

// Map fill for each side of an issue (+1 / 0 / -1). Teal and purple rather
// than red and blue, so a side doesn't read as a party.
export const SIDE_COLORS = { 1: '#35b9a6', 0: '#5d6782', [-1]: '#a35ccc' }

// Ordered choices for a position picker.
export const POSITION_CHOICES = [
  { value: 1, key: 'pro' },
  { value: 0, key: 'mid' },
  { value: -1, key: 'con' },
]
