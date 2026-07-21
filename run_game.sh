#!/usr/bin/env bash
#
# Convenience launcher for Campaign Game and its test suite.
#
# Usage:
#   ./run_game.sh              Launch the game (Tkinter GUI).
#   ./run_game.sh --debug      Launch with verbose per-week rules logging
#                              (sets CAMPAIGN_DEBUG=1; also writes to logs/).
#   ./run_game.sh --test       Run the automated engine parity + golden tests.
#   ./run_game.sh --sim        Run the headless sim + RL smoke checks.
#   ./run_game.sh --all-checks  --test then --sim.
#
# Any extra args after a launch (no flag / --debug) are passed through to
# `python CampaignGame.py`.
#
# The GUI needs a display. On Windows 11 + WSL, WSLg provides one out of the
# box. If the window doesn't appear, run instead from native Windows Python
# (which ships Tkinter):  python CampaignGame.py
#
set -euo pipefail

# Always operate from the repo root (this script's directory) so relative
# data-file paths resolve regardless of where it's invoked from.
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

if ! command -v "$PY" >/dev/null 2>&1; then
    echo "error: '$PY' not found on PATH. Set PYTHON=... to override." >&2
    exit 1
fi

run_tests() {
    echo "== engine parity + golden tests =="
    "$PY" tests/test_engine_parity.py
}

run_sim_smoke() {
    echo "== headless sim: one full game =="
    "$PY" -c "import sim_balance as sb; s=sb.run_game(sb.ALL_STRATEGIES[:4], num_turns=10, seed=1); print('  ok - top delegates:', round(max(p.delegate_count for p in s.players)))"
    echo "== balance tournament (small) =="
    "$PY" -c "import sim_balance as sb; rows=sb.run_tournament(sb.ALL_STRATEGIES[:4], n_games_per_seat=3, num_turns=10, seed_base=7, seats=2); sb.print_table(sb.aggregate(rows),'smoke')"
    echo "== RL env rollout (20 games) =="
    "$PY" -m rl.smoke_test
}

case "${1:-}" in
    --test)
        run_tests
        ;;
    --sim)
        run_sim_smoke
        ;;
    --all-checks)
        run_tests
        echo
        run_sim_smoke
        ;;
    --debug)
        shift
        echo "Launching Campaign Game (CAMPAIGN_DEBUG=1)..."
        CAMPAIGN_DEBUG=1 exec "$PY" CampaignGame.py "$@"
        ;;
    -h|--help)
        sed -n '2,20p' "$0"
        ;;
    *)
        echo "Launching Campaign Game..."
        exec "$PY" CampaignGame.py "$@"
        ;;
esac
