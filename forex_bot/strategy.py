"""The trading rules, and the shared "how would this trade have played out"
simulator used by both the backtester and the AI filter's training labels.

Rule (trend following):
  BUY  when the fast EMA crosses above the slow EMA, price is above the
       200 EMA (long-term uptrend), and RSI isn't already overbought.
  SELL the mirror image.
A signal is decided at a candle's close and entered at the next candle's open.
"""
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from .config import Settings
from .indicators import atr, ema, rsi


def add_indicators(df: pd.DataFrame, s: Settings) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = ema(out["close"], s.fast_ema)
    out["ema_slow"] = ema(out["close"], s.slow_ema)
    out["ema_trend"] = ema(out["close"], s.trend_ema)
    out["rsi"] = rsi(out["close"], s.rsi_period)
    out["atr"] = atr(out, s.atr_period)
    return out


def generate_signals(ind: pd.DataFrame, s: Settings) -> pd.Series:
    """+1 buy, -1 sell, 0 nothing, per bar. `ind` comes from add_indicators."""
    fast, slow = ind["ema_fast"], ind["ema_slow"]
    cross_up = (fast > slow) & (fast.shift() <= slow.shift())
    cross_down = (fast < slow) & (fast.shift() >= slow.shift())
    lo, hi = s.rsi_long_range
    long_ok = cross_up & (ind["close"] > ind["ema_trend"]) & ind["rsi"].between(lo, hi)
    lo, hi = s.rsi_short_range
    short_ok = cross_down & (ind["close"] < ind["ema_trend"]) & ind["rsi"].between(lo, hi)
    sig = pd.Series(0, index=ind.index, dtype=int)
    sig[long_ok] = 1
    sig[short_ok] = -1
    # The 200 EMA needs time to settle before it means anything.
    sig.iloc[: s.trend_ema] = 0
    return sig


@dataclass
class TradeOutcome:
    entry_idx: int
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_idx: Optional[int]  # None = still open when the data ran out
    exit_price: float
    reason: str  # "tp", "sl", "timeout", "open"

    @property
    def resolved(self) -> bool:
        return self.exit_idx is not None


def simulate_trade(ind: pd.DataFrame, signal_idx: int, direction: int,
                   s: Settings) -> Optional[TradeOutcome]:
    """Play out a trade signalled at bar `signal_idx` (entered next bar open).

    Prices in `ind` are mid prices; half the spread is paid on entry and half
    on exit. If a single candle touches both the stop and the target we
    assume the stop hit first - the pessimistic choice.
    """
    entry_idx = signal_idx + 1
    if entry_idx >= len(ind):
        return None
    half = s.spread_pips * s.pip_size / 2
    o, h, l, c = (ind[k].to_numpy() for k in ("open", "high", "low", "close"))
    risk = s.sl_atr * float(ind["atr"].iloc[signal_idx])
    reward = s.tp_atr * float(ind["atr"].iloc[signal_idx])

    entry = o[entry_idx] + direction * half
    sl = entry - direction * risk
    tp = entry + direction * reward
    last = min(entry_idx + s.max_hold_bars - 1, len(ind) - 1)

    for j in range(entry_idx, last + 1):
        # Price we could exit at: bid for a long, ask for a short.
        if direction == 1:
            ex_open, ex_low, ex_high = o[j] - half, l[j] - half, h[j] - half
            if j > entry_idx and ex_open <= sl:  # gapped through the stop
                return TradeOutcome(entry_idx, entry, sl, tp, j, ex_open, "sl")
            if ex_low <= sl:
                return TradeOutcome(entry_idx, entry, sl, tp, j, sl, "sl")
            if ex_high >= tp:
                return TradeOutcome(entry_idx, entry, sl, tp, j, tp, "tp")
        else:
            ex_open, ex_low, ex_high = o[j] + half, l[j] + half, h[j] + half
            if j > entry_idx and ex_open >= sl:
                return TradeOutcome(entry_idx, entry, sl, tp, j, ex_open, "sl")
            if ex_high >= sl:
                return TradeOutcome(entry_idx, entry, sl, tp, j, sl, "sl")
            if ex_low <= tp:
                return TradeOutcome(entry_idx, entry, sl, tp, j, tp, "tp")

    exit_price = c[last] - direction * half
    if last == entry_idx + s.max_hold_bars - 1:
        return TradeOutcome(entry_idx, entry, sl, tp, last, exit_price, "timeout")
    return TradeOutcome(entry_idx, entry, sl, tp, None, exit_price, "open")


def r_multiple(t: TradeOutcome, direction: int) -> float:
    """Profit in units of the amount risked: +2.0 = won twice the risk."""
    risk = abs(t.entry_price - t.stop_loss)
    return direction * (t.exit_price - t.entry_price) / risk if risk else 0.0


def signal_positions(signals: pd.Series) -> np.ndarray:
    return np.flatnonzero(signals.to_numpy() != 0)
