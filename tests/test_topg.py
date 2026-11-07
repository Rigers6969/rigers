"""TOP G War Room: the streak counts days in a row with every task done."""
from datetime import date, timedelta

import topg_api


def test_streak():
    today = date(2026, 11, 8)
    d = {"tasks": ["a", "b"], "days": {}}
    day = lambda n: (today - timedelta(days=n)).isoformat()
    d["days"][day(1)] = [True, True]
    d["days"][day(2)] = [True, True]
    d["days"][day(3)] = [True, False]
    assert topg_api.streak(d, today) == 2          # today not finished yet: still counts yesterday's run
    d["days"][day(0)] = [True, True]
    assert topg_api.streak(d, today) == 3
    d["days"][day(1)] = [False, True]
    assert topg_api.streak(d, today) == 1          # a broken day resets it
