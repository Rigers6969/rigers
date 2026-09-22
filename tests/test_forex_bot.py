"""Tests for forex_bot. Fully offline - OANDA is mocked, prices are synthetic
or hand-built."""
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forex_bot.ai_filter import build_features, walk_forward  # noqa: E402
from forex_bot.backtest import run_backtest  # noqa: E402
from forex_bot.broker import OandaClient, OandaError  # noqa: E402
from forex_bot.config import Settings  # noqa: E402
from forex_bot.data import synthetic_candles  # noqa: E402
from forex_bot.indicators import atr, ema, rsi  # noqa: E402
from forex_bot.live import LiveTrader  # noqa: E402
from forex_bot.risk import daily_loss_hit, position_units  # noqa: E402
from forex_bot.strategy import (add_indicators, generate_signals,  # noqa: E402
                                signal_positions, simulate_trade)


def flat_bars(n, price=1.0):
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame({"open": price, "high": price, "low": price, "close": price}, index=idx)


def trade_settings(**kw):
    s = Settings(spread_pips=0.0, sl_atr=1.0, tp_atr=2.0, max_hold_bars=5)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


class TestIndicators(unittest.TestCase):
    def test_ema_first_value_and_recursion(self):
        s = pd.Series([1.0, 2.0, 3.0])
        e = ema(s, 3)  # alpha = 0.5
        self.assertAlmostEqual(e.iloc[1], 1.5)
        self.assertAlmostEqual(e.iloc[2], 2.25)

    def test_rsi_bounds_and_direction(self):
        up = pd.Series(np.linspace(1, 2, 50))
        self.assertGreater(rsi(up).iloc[-1], 99)
        r = rsi(pd.Series(np.random.default_rng(0).normal(0, 1, 300)).cumsum() + 100)
        self.assertTrue(((r >= 0) & (r <= 100)).all())

    def test_atr_of_constant_range(self):
        df = flat_bars(30)
        df["high"], df["low"] = 1.01, 0.99
        self.assertAlmostEqual(atr(df, 14).iloc[-1], 0.02)

    def test_indicators_are_causal(self):
        df = synthetic_candles(800, seed=1)
        s = Settings()
        full = add_indicators(df, s)
        part = add_indicators(df.iloc[:500], s)
        pd.testing.assert_frame_equal(full.iloc[:500], part)
        pd.testing.assert_series_equal(generate_signals(full, s).iloc[:500], generate_signals(part, s))
        sig_full, sig_part = generate_signals(full, s), generate_signals(part, s)
        pd.testing.assert_frame_equal(build_features(full, sig_full).iloc[:500],
                                      build_features(part, sig_part))


class TestSimulateTrade(unittest.TestCase):
    def setUp(self):
        self.df = flat_bars(10)
        self.df["atr"] = 0.01  # stop 0.01 away, target 0.02 away

    def test_take_profit(self):
        self.df.loc[self.df.index[3], "high"] = 1.03
        t = simulate_trade(self.df, 0, 1, trade_settings())
        self.assertEqual((t.reason, t.exit_idx, t.exit_price), ("tp", 3, 1.02))

    def test_stop_loss_short(self):
        self.df.loc[self.df.index[2], "high"] = 1.015
        t = simulate_trade(self.df, 0, -1, trade_settings())
        self.assertEqual((t.reason, t.exit_idx), ("sl", 2))
        self.assertAlmostEqual(t.exit_price, 1.01)

    def test_both_hit_same_bar_assumes_stop(self):
        self.df.loc[self.df.index[2], ["high", "low"]] = [1.05, 0.95]
        self.assertEqual(simulate_trade(self.df, 0, 1, trade_settings()).reason, "sl")

    def test_gap_through_stop_fills_at_open(self):
        self.df.loc[self.df.index[2], ["open", "high", "low", "close"]] = [0.97, 0.97, 0.96, 0.97]
        t = simulate_trade(self.df, 0, 1, trade_settings())
        self.assertEqual((t.reason, t.exit_price), ("sl", 0.97))

    def test_timeout_and_unresolved(self):
        t = simulate_trade(self.df, 0, 1, trade_settings())
        self.assertEqual((t.reason, t.exit_idx), ("timeout", 5))
        t = simulate_trade(self.df, 7, 1, trade_settings())
        self.assertFalse(t.resolved)
        self.assertIsNone(simulate_trade(self.df, 9, 1, trade_settings()))

    def test_spread_is_paid(self):
        s = trade_settings(spread_pips=2.0)
        t = simulate_trade(self.df, 0, 1, s)
        self.assertAlmostEqual(t.entry_price, 1.0001)
        self.assertAlmostEqual(t.exit_price, 0.9999)


class TestWalkForwardNoLookahead(unittest.TestCase):
    def test_probabilities_do_not_depend_on_future_bars(self):
        s = Settings(ai_min_train=15, ai_retrain_every=5)
        df = synthetic_candles(5000, seed=3)

        def probs_for(data):
            ind = add_indicators(data, s)
            sig = generate_signals(ind, s)
            pos = signal_positions(sig).tolist()
            dirs = {i: int(sig.iloc[i]) for i in pos}
            outs = {i: simulate_trade(ind, i, dirs[i], s) for i in pos}
            return walk_forward(build_features(ind, sig), pos, dirs, outs, s)

        full = probs_for(df)
        ready = [i for i, p in full.items() if p is not None]
        self.assertTrue(ready, "model never became ready - test data too short")
        for i in ready[:: max(1, len(ready) // 5)]:
            self.assertAlmostEqual(probs_for(df.iloc[: i + 1])[i], full[i])


class TestRisk(unittest.TestCase):
    def test_eur_usd_sizing(self):
        # $10k, 1% risk = $100, stop 15 pips -> 66,666 units
        self.assertEqual(position_units(10_000, 0.01, 0.0015, "EUR_USD", 1.1, 10), 66_666)

    def test_usd_jpy_sizing(self):
        # stop 0.15 yen at 150 -> $0.001 per unit -> 100,000 units
        self.assertEqual(position_units(10_000, 0.01, 0.15, "USD_JPY", 150.0, 50), 100_000)

    def test_leverage_cap(self):
        self.assertEqual(position_units(10_000, 0.01, 0.0001, "EUR_USD", 1.0, 5), 50_000)

    def test_bad_inputs(self):
        self.assertEqual(position_units(0, 0.01, 0.001, "EUR_USD", 1.1, 10), 0)
        with self.assertRaises(ValueError):
            position_units(10_000, 0.01, 0.001, "EUR_GBP", 0.85, 10)

    def test_daily_loss(self):
        self.assertFalse(daily_loss_hit(10_000, 9_800, 0.03))
        self.assertTrue(daily_loss_hit(10_000, 9_700, 0.03))

    def test_settings_validation(self):
        with self.assertRaises(ValueError):
            Settings(instrument="EUR_GBP").validate()
        with self.assertRaises(ValueError):
            Settings(risk_per_trade=0.2).validate()


class TestBacktest(unittest.TestCase):
    def test_balance_matches_trades_and_one_at_a_time(self):
        s = Settings()
        df = synthetic_candles(4000, seed=5)
        for use_ai in (False, True):
            res = run_backtest(df, s, use_ai=use_ai)
            self.assertGreater(len(res.trades), 10)
            self.assertAlmostEqual(res.end_balance, 10_000 + sum(t.pnl for t in res.trades), places=6)
            times = [t.time for t in res.trades]
            self.assertEqual(times, sorted(times))
            st = res.stats()
            self.assertGreaterEqual(st["max_drawdown_pct"], 0)

    def test_losses_are_about_one_percent(self):
        res = run_backtest(synthetic_candles(4000, seed=5), Settings(), use_ai=False)
        stop_losses = [t for t in res.trades if t.reason == "sl"]
        self.assertTrue(stop_losses)
        for t in stop_losses[:20]:
            self.assertLess(abs(t.r + 1), 0.35)  # ~-1R, gaps can make it a bit worse


def mock_response(status=200, payload=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload or {}
    r.text = str(payload)
    return r


class TestOandaClient(unittest.TestCase):
    def make(self, env="practice"):
        session = MagicMock()
        session.headers = {}
        return OandaClient("tok", "001-001", env, session=session), session

    def test_requires_token(self):
        with self.assertRaises(OandaError):
            OandaClient("", "x")

    def test_candles_drop_incomplete(self):
        c, sess = self.make()
        sess.request.return_value = mock_response(payload={"candles": [
            {"time": "2024-01-01T00:00:00.000000000Z", "complete": True,
             "mid": {"o": "1.1", "h": "1.2", "l": "1.0", "c": "1.15"}},
            {"time": "2024-01-01T01:00:00.000000000Z", "complete": False,
             "mid": {"o": "1.15", "h": "1.2", "l": "1.1", "c": "1.16"}},
        ]})
        df = c.candles("EUR_USD", "H1", 2)
        self.assertEqual(len(df), 1)
        self.assertEqual(df["close"].iloc[0], 1.15)
        self.assertEqual(sess.request.call_args.args[1],
                         "https://api-fxpractice.oanda.com/v3/instruments/EUR_USD/candles")

    def test_market_order_payload(self):
        c, sess = self.make()
        sess.request.side_effect = [
            mock_response(payload={"instruments": [{"displayPrecision": 5}]}),
            mock_response(payload={"orderFillTransaction": {}}),
        ]
        c.market_order("EUR_USD", -1000, 0.0015, 0.003)
        order = sess.request.call_args.kwargs["json"]["order"]
        self.assertEqual(order["units"], "-1000")
        self.assertEqual(order["stopLossOnFill"]["distance"], "0.00150")
        self.assertEqual(order["takeProfitOnFill"]["distance"], "0.00300")

    def test_errors_raise(self):
        c, sess = self.make()
        sess.request.return_value = mock_response(400, {"errorMessage": "bad"})
        with self.assertRaisesRegex(OandaError, "bad"):
            c.account_summary()
        c._precision["EUR_USD"] = 5
        sess.request.return_value = mock_response(payload={"orderCancelTransaction": {"reason": "MARKET_HALTED"}})
        with self.assertRaisesRegex(OandaError, "MARKET_HALTED"):
            c.market_order("EUR_USD", 1000, 0.001, 0.002)


class TestLiveTrader(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.s = Settings(history_bars=3000)
        self.candles = synthetic_candles(3000, seed=11)
        # Find a bar with a signal and cut the history there, so the latest bar signals.
        ind = add_indicators(self.candles, self.s)
        last_sig = signal_positions(generate_signals(ind, self.s))[-1]
        self.candles = self.candles.iloc[: last_sig + 1]

    def trader(self, env="practice", dry_run=True, allow_live=False):
        client = MagicMock()
        client.env = env
        client.candles_history.return_value = self.candles
        client.account_summary.return_value = {"NAV": "10000"}
        client.open_trades.return_value = []
        self.s.allow_live = allow_live
        self.s.use_ai_filter = False
        t = LiveTrader(client, self.s, dry_run=dry_run, stop_file=self.tmp / "STOP",
                       state_file=self.tmp / "state.json", journal_file=self.tmp / "journal.csv",
                       log=lambda m: None)
        return t, client

    def test_refuses_live_without_opt_in(self):
        with self.assertRaises(OandaError):
            self.trader(env="live")
        self.trader(env="live", allow_live=True)

    def test_kill_switch(self):
        t, client = self.trader()
        (self.tmp / "STOP").touch()
        self.assertIn("kill switch", t.step())
        client.candles_history.assert_not_called()

    def test_dry_run_journals_but_sends_nothing(self):
        t, client = self.trader(dry_run=True)
        msg = t.step()
        self.assertIn("[dry run]", msg)
        client.market_order.assert_not_called()
        self.assertTrue((self.tmp / "journal.csv").exists())
        self.assertEqual(t.step(), "waiting for the next candle")

    def test_places_order_with_protection(self):
        t, client = self.trader(dry_run=False)
        t.step()
        args = client.market_order.call_args.args
        self.assertEqual(args[0], "EUR_USD")
        self.assertNotEqual(args[1], 0)
        self.assertGreater(args[2], 0)
        self.assertAlmostEqual(args[3], 2 * args[2])

    def test_skips_when_in_trade_or_daily_limit(self):
        t, client = self.trader(dry_run=False)
        client.open_trades.return_value = [{"id": "1"}]
        self.assertIn("already in a trade", t.step())
        t2, client2 = self.trader(dry_run=False)
        t2.state = {"day": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "day_start_nav": 11_000}
        self.assertIn("daily loss limit", t2.step())
        client.market_order.assert_not_called()
        client2.market_order.assert_not_called()

    def test_ai_filter_path_runs(self):
        t, client = self.trader(dry_run=True)
        self.s.use_ai_filter = True
        self.s.ai_threshold = 1.01  # impossible bar: anything scored gets vetoed
        msg = t.step()
        self.assertTrue("vetoed by AI" in msg or "still learning" in msg, msg)


if __name__ == "__main__":
    unittest.main()
