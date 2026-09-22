"""Where candles come from: OANDA (real data), a CSV file, or a synthetic
generator for trying the bot out with no account and no internet.

All sources return the same shape: a DataFrame indexed by UTC time with
open/high/low/close columns (mid prices).
"""
import numpy as np
import pandas as pd

COLUMNS = ["open", "high", "low", "close"]


def load_csv(path: str) -> pd.DataFrame:
    """CSV with a time/date column plus open, high, low, close (any case)."""
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    time_col = next((c for c in ("time", "datetime", "date", "timestamp") if c in df.columns), None)
    if time_col is None:
        raise ValueError(f"{path}: needs a time/datetime/date/timestamp column")
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    df.index = pd.to_datetime(df[time_col], utc=True)
    return df[COLUMNS].astype(float).sort_index()


def synthetic_candles(n: int = 6000, seed: int = 7, start_price: float = 1.10,
                      freq: str = "h") -> pd.DataFrame:
    """Fake EUR/USD-like hourly candles with trending and choppy stretches.

    For demos and tests only. Results on this data say nothing about how the
    bot would do in the real market.
    """
    rng = np.random.default_rng(seed)
    steps = 12
    drift = np.zeros(n)
    i = 0
    while i < n:
        length = int(rng.integers(100, 500))
        drift[i:i + length] = rng.choice([-1, 0, 0, 1]) * rng.uniform(0.00002, 0.00008)
        i += length
    vol = 0.0009 * np.exp(rng.normal(0, 0.25, n))
    moves = rng.normal(drift[:, None] / steps, vol[:, None] / np.sqrt(steps), (n, steps))
    path = start_price * np.exp(np.cumsum(moves.ravel())).reshape(n, steps)
    opens = np.concatenate([[start_price], path[:-1, -1]])
    df = pd.DataFrame({
        "open": opens,
        "high": np.maximum(path.max(axis=1), opens),
        "low": np.minimum(path.min(axis=1), opens),
        "close": path[:, -1],
    }, index=pd.date_range("2024-01-01", periods=n, freq=freq, tz="UTC"))
    return df
