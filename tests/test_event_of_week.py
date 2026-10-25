"""Issue-of-the-week rolls: random, but never the same issue two weeks running.

Run:  python -m pytest tests/test_event_of_week.py
"""
import collections
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine  # noqa: E402


def test_never_repeats_previous_week():
    rng = random.Random(0)
    prev = 0
    for _ in range(20000):
        nxt = engine.next_event_of_week(rng, 8, prev)
        assert nxt != prev
        assert 0 <= nxt < 8
        prev = nxt


def test_uniform_over_the_other_issues():
    rng = random.Random(1)
    counts = collections.Counter(engine.next_event_of_week(rng, 8, 3) for _ in range(70000))
    assert counts[3] == 0
    for issue in range(8):
        if issue != 3:
            assert abs(counts[issue] / 70000 - 1 / 7) < 0.01


def test_falls_back_to_plain_roll():
    rng = random.Random(2)
    assert 0 <= engine.next_event_of_week(rng, 8, None) < 8   # no previous week
    assert engine.next_event_of_week(rng, 1, 0) == 0          # only one issue
