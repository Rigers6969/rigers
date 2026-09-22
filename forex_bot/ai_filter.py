"""The "AI" part: a machine-learning model that learns, from the bot's own
past trade ideas, which setups tended to win - and vetoes the weak ones.

It's deliberately a simple, heavily-regularised model (logistic regression).
With a few hundred examples at most, anything fancier just memorises noise.

The golden rule, enforced here: when deciding on a trade at bar i, the model
may only have been trained on trades that had *already finished* by bar i.
"""
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .config import Settings
from .strategy import TradeOutcome, r_multiple

FEATURES = [
    "ret_1", "ret_4", "ret_12", "ret_24",
    "dist_fast", "dist_slow", "dist_trend",
    "rsi_dir", "atr_ratio", "hour_sin", "hour_cos", "direction",
]


def build_features(ind: pd.DataFrame, signals: pd.Series) -> pd.DataFrame:
    """One row per bar describing the market at that bar's close.

    Direction-sensitive features are flipped for sells, so "price moving my
    way" looks the same to the model whether it's a buy or a sell.
    """
    d = signals.replace(0, np.nan).astype(float)
    close, a = ind["close"], ind["atr"]
    f = pd.DataFrame(index=ind.index)
    for k in (1, 4, 12, 24):
        f[f"ret_{k}"] = (close - close.shift(k)) / a * d
    f["dist_fast"] = (close - ind["ema_fast"]) / a * d
    f["dist_slow"] = (close - ind["ema_slow"]) / a * d
    f["dist_trend"] = (close - ind["ema_trend"]) / a * d
    f["rsi_dir"] = (ind["rsi"] - 50) / 50 * d
    f["atr_ratio"] = a / a.rolling(100, min_periods=20).mean()
    hours = ind.index.hour if isinstance(ind.index, pd.DatetimeIndex) else np.zeros(len(ind))
    f["hour_sin"] = np.sin(2 * np.pi * np.asarray(hours) / 24)
    f["hour_cos"] = np.cos(2 * np.pi * np.asarray(hours) / 24)
    f["direction"] = d
    return f.replace([np.inf, -np.inf], np.nan).fillna(0.0)[FEATURES]


class AIFilter:
    def __init__(self, s: Settings):
        self.s = s
        self.model = None
        self.trained_on = 0

    def fit(self, X: np.ndarray, y: np.ndarray) -> bool:
        """Returns False (and stays untrained) if there's not enough data."""
        if len(y) < self.s.ai_min_train or len(set(y.tolist())) < 2:
            return False
        self.model = make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=1000))
        self.model.fit(X, y)
        self.trained_on = len(y)
        return True

    @property
    def ready(self) -> bool:
        return self.model is not None

    def win_probability(self, x: np.ndarray) -> Optional[float]:
        if not self.ready:
            return None
        return float(self.model.predict_proba(x.reshape(1, -1))[0, 1])

    def approves(self, prob: Optional[float]) -> bool:
        # Until trained, the filter stays out of the way and the plain rules trade.
        return prob is None or prob >= self.s.ai_threshold


def label(outcome: TradeOutcome, direction: int) -> int:
    """1 if the trade made money (after spread), else 0."""
    return int(r_multiple(outcome, direction) > 0)


def walk_forward(features: pd.DataFrame, positions: List[int], directions: Dict[int, int],
                 outcomes: Dict[int, Optional[TradeOutcome]], s: Settings) -> Dict[int, Optional[float]]:
    """Win probability for each signal bar, using only trades finished before it.

    Returns {bar position: probability or None if the model wasn't ready yet}.
    """
    X_all = features.to_numpy()
    filt = AIFilter(s)
    probs: Dict[int, Optional[float]] = {}
    for i in positions:
        done = [j for j in positions
                if j < i and outcomes.get(j) is not None
                and outcomes[j].resolved and outcomes[j].exit_idx <= i]
        due = (not filt.ready and len(done) >= s.ai_min_train) or \
              (filt.ready and len(done) - filt.trained_on >= s.ai_retrain_every)
        if due:
            y = np.array([label(outcomes[j], directions[j]) for j in done])
            filt.fit(X_all[done], y)
        probs[i] = filt.win_probability(X_all[i])
    return probs
