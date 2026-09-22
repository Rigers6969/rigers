"""Replay the strategy over historical candles and report how it would have done.

Realism built in: next-bar entries, spread on every trade, stop assumed to
hit first on ambiguous candles, one trade at a time, 1% risk sizing, daily
loss limit, and an AI filter trained walk-forward (never on the future).
A backtest is still only an estimate - live results are usually worse.
"""
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

from .ai_filter import build_features, walk_forward
from .config import Settings
from .risk import daily_loss_hit, position_units, quote_to_account
from .strategy import (TradeOutcome, add_indicators, generate_signals,
                       r_multiple, signal_positions, simulate_trade)


@dataclass
class Trade:
    time: pd.Timestamp
    direction: int
    units: int
    entry: float
    exit: float
    reason: str
    pnl: float
    r: float
    ai_prob: Optional[float]


@dataclass
class BacktestResult:
    start_balance: float
    trades: List[Trade] = field(default_factory=list)
    equity: List[float] = field(default_factory=list)
    signals_seen: int = 0
    ai_rejected: int = 0
    skipped_busy: int = 0
    skipped_daily_limit: int = 0

    @property
    def end_balance(self) -> float:
        return self.equity[-1] if self.equity else self.start_balance

    def stats(self) -> dict:
        pnls = np.array([t.pnl for t in self.trades])
        wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
        curve = np.array([self.start_balance] + self.equity)
        peak = np.maximum.accumulate(curve)
        return {
            "trades": len(self.trades),
            "win_rate_pct": 100 * len(wins) / len(pnls) if len(pnls) else 0.0,
            "total_return_pct": 100 * (self.end_balance / self.start_balance - 1),
            "profit_factor": wins.sum() / -losses.sum() if losses.sum() < 0 else float("inf") if len(wins) else 0.0,
            "avg_r": float(np.mean([t.r for t in self.trades])) if self.trades else 0.0,
            "max_drawdown_pct": float(100 * ((peak - curve) / peak).max()),
            "end_balance": self.end_balance,
            "signals_seen": self.signals_seen,
            "ai_rejected": self.ai_rejected,
            "skipped_busy": self.skipped_busy,
            "skipped_daily_limit": self.skipped_daily_limit,
        }


def run_backtest(candles: pd.DataFrame, s: Settings, use_ai: Optional[bool] = None,
                 start_balance: float = 10_000.0) -> BacktestResult:
    use_ai = s.use_ai_filter if use_ai is None else use_ai
    ind = add_indicators(candles, s)
    signals = generate_signals(ind, s)
    positions = signal_positions(signals).tolist()
    directions = {i: int(signals.iloc[i]) for i in positions}
    outcomes = {i: simulate_trade(ind, i, directions[i], s) for i in positions}

    probs = {}
    if use_ai:
        probs = walk_forward(build_features(ind, signals), positions, directions, outcomes, s)

    res = BacktestResult(start_balance)
    balance = start_balance
    busy_until = -1
    day, day_start = None, balance
    has_dates = isinstance(ind.index, pd.DatetimeIndex)

    for i in positions:
        res.signals_seen += 1
        outcome: Optional[TradeOutcome] = outcomes[i]
        if outcome is None:
            continue
        if i < busy_until:
            res.skipped_busy += 1
            continue
        today = ind.index[outcome.entry_idx].date() if has_dates else outcome.entry_idx // 24
        if today != day:
            day, day_start = today, balance
        if daily_loss_hit(day_start, balance, s.max_daily_loss):
            res.skipped_daily_limit += 1
            continue
        prob = probs.get(i)
        if use_ai and prob is not None and prob < s.ai_threshold:
            res.ai_rejected += 1
            continue

        d = directions[i]
        units = position_units(balance, s.risk_per_trade, abs(outcome.entry_price - outcome.stop_loss),
                               s.instrument, outcome.entry_price, s.max_leverage)
        if units == 0:
            continue
        pnl = units * d * (outcome.exit_price - outcome.entry_price) * \
            quote_to_account(s.instrument, outcome.exit_price)
        balance += pnl
        res.trades.append(Trade(ind.index[outcome.entry_idx], d, units, outcome.entry_price,
                                outcome.exit_price, outcome.reason, pnl, r_multiple(outcome, d), prob))
        res.equity.append(balance)
        busy_until = outcome.exit_idx if outcome.resolved else len(ind)
    return res


def format_stats(name: str, st: dict) -> str:
    pf = st["profit_factor"]
    pf_txt = "inf" if pf == float("inf") else f"{pf:.2f}"
    return (
        f"{name}\n"
        f"  trades taken      {st['trades']}  (signals {st['signals_seen']}, "
        f"AI vetoed {st['ai_rejected']}, busy {st['skipped_busy']}, daily-limit {st['skipped_daily_limit']})\n"
        f"  win rate          {st['win_rate_pct']:.1f}%\n"
        f"  total return      {st['total_return_pct']:+.2f}%   (end balance ${st['end_balance']:,.2f})\n"
        f"  profit factor     {pf_txt}   (>1.0 = made money; aim for >1.3)\n"
        f"  avg trade         {st['avg_r']:+.2f}R  (R = amount risked per trade)\n"
        f"  max drawdown      {st['max_drawdown_pct']:.1f}%"
    )
