"""The live loop: once per new candle, look for a signal, ask the AI filter,
check the risk limits, and (unless dry-running) place the order on OANDA.

Safety:
  * practice (demo) account unless FOREX_ALLOW_LIVE=yes AND OANDA_ENV=live
  * every order carries a stop-loss and take-profit set by OANDA itself,
    so positions stay protected even if this program crashes
  * create a file called STOP in the forex_bot folder to halt new trades
  * daily loss limit, one trade at a time, 1% risk per trade
"""
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .ai_filter import AIFilter, build_features, label
from .broker import OandaClient, OandaError
from .config import Settings
from .risk import daily_loss_hit, position_units
from .strategy import add_indicators, generate_signals, signal_positions, simulate_trade

BOT_DIR = Path(__file__).resolve().parent
STOP_FILE = BOT_DIR / "STOP"
STATE_FILE = BOT_DIR / "state.json"
JOURNAL_FILE = BOT_DIR / "journal.csv"


class LiveTrader:
    def __init__(self, client: OandaClient, s: Settings, dry_run: bool = False,
                 stop_file: Path = STOP_FILE, state_file: Path = STATE_FILE,
                 journal_file: Path = JOURNAL_FILE, log: Callable[[str], None] = print):
        if client.env == "live" and not s.allow_live:
            raise OandaError(
                "Refusing to trade a LIVE (real-money) account. Practise on a demo "
                "account first. If you really mean it, set FOREX_ALLOW_LIVE=yes."
            )
        self.client, self.s, self.dry_run = client, s, dry_run
        self.stop_file, self.state_file, self.journal_file = stop_file, state_file, journal_file
        self.log = log
        self.last_bar = None
        self.state = self._load_state()

    def _load_state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            return {}

    def _save_state(self) -> None:
        try:
            self.state_file.write_text(json.dumps(self.state))
        except OSError as e:
            self.log(f"warning: could not save state: {e}")

    def _journal(self, row: dict) -> None:
        new = not self.journal_file.exists()
        with self.journal_file.open("a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(row))
            if new:
                w.writeheader()
            w.writerow(row)

    def _day_start_nav(self, nav: float, now: datetime) -> float:
        today = now.strftime("%Y-%m-%d")
        if self.state.get("day") != today:
            self.state = {"day": today, "day_start_nav": nav}
            self._save_state()
        return float(self.state["day_start_nav"])

    def step(self, now: Optional[datetime] = None) -> str:
        """Run one check. Returns a short description of what happened."""
        now = now or datetime.now(timezone.utc)
        s = self.s
        if self.stop_file.exists():
            return f"kill switch on ({self.stop_file.name} file exists) - not trading"

        candles = self.client.candles_history(s.instrument, s.granularity, s.history_bars)
        if len(candles) < s.trend_ema + 50:
            return f"not enough history yet ({len(candles)} candles)"
        bar_time = candles.index[-1]
        if bar_time == self.last_bar:
            return "waiting for the next candle"
        self.last_bar = bar_time

        ind = add_indicators(candles, s)
        signals = generate_signals(ind, s)
        last = len(ind) - 1
        direction = int(signals.iloc[last])
        if direction == 0:
            return f"{bar_time:%Y-%m-%d %H:%M} no signal"
        side = "BUY" if direction == 1 else "SELL"

        prob = None
        if s.use_ai_filter:
            prob = self._ai_probability(ind, signals, last)
            if prob is not None and prob < s.ai_threshold:
                return f"{side} signal vetoed by AI (win chance {prob:.0%} < {s.ai_threshold:.0%})"

        summary = self.client.account_summary()
        nav = float(summary["NAV"])
        if daily_loss_hit(self._day_start_nav(nav, now), nav, s.max_daily_loss):
            return f"{side} signal skipped - daily loss limit reached"
        if len(self.client.open_trades(s.instrument)) >= s.max_open_trades:
            return f"{side} signal skipped - already in a trade"

        a = float(ind["atr"].iloc[last])
        price = float(ind["close"].iloc[last])
        stop_dist, tp_dist = s.sl_atr * a, s.tp_atr * a
        units = position_units(nav, s.risk_per_trade, stop_dist, s.instrument, price, s.max_leverage)
        if units == 0:
            return f"{side} signal skipped - position size rounds to 0"

        prob_txt = "n/a (still learning)" if prob is None else f"{prob:.0%}"
        msg = (f"{side} {units} {s.instrument} ~{price:.5f}  stop {stop_dist:.5f} away, "
               f"target {tp_dist:.5f} away, AI win chance {prob_txt}")
        if self.dry_run:
            msg = "[dry run] " + msg
        else:
            self.client.market_order(s.instrument, direction * units, stop_dist, tp_dist)
        self._journal({
            "time": now.isoformat(), "bar": bar_time.isoformat(), "side": side,
            "units": units, "price": price, "stop_distance": stop_dist,
            "tp_distance": tp_dist, "ai_prob": "" if prob is None else round(prob, 4),
            "dry_run": self.dry_run, "env": self.client.env,
        })
        return msg

    def _ai_probability(self, ind, signals, last: int) -> Optional[float]:
        """Train on every earlier signal that has fully played out, score the newest."""
        feats = build_features(ind, signals).to_numpy()
        done, ys = [], []
        for i in signal_positions(signals):
            if i >= last:
                continue
            d = int(signals.iloc[i])
            out = simulate_trade(ind, i, d, self.s)
            if out is not None and out.resolved and out.exit_idx <= last:
                done.append(i)
                ys.append(label(out, d))
        filt = AIFilter(self.s)
        if not filt.fit(feats[done], np.array(ys)):
            return None
        return filt.win_probability(feats[last])

    def run_forever(self) -> None:
        mode = "DRY RUN (no orders sent)" if self.dry_run else f"{self.client.env.upper()} account"
        self.log(f"Forex bot started: {self.s.instrument} {self.s.granularity}, {mode}. Ctrl+C to stop.")
        while True:
            try:
                self.log(f"{datetime.now():%H:%M:%S}  {self.step()}")
            except (OandaError, OSError) as e:
                self.log(f"{datetime.now():%H:%M:%S}  error: {e} - will retry")
            time.sleep(self.s.poll_seconds)
