"""All tunable settings in one place.

Everything has a safe default. The few things a beginner might want to
change (which currency pair, how much to risk) can also be set in .env -
see .env.example.
"""
import os
from dataclasses import dataclass, field

# OANDA account currency. Position sizing assumes USD is one side of the
# pair (EUR_USD, GBP_USD, USD_JPY, ...), which covers all the major pairs.
ACCOUNT_CURRENCY = "USD"


@dataclass
class Settings:
    # What to trade. OANDA writes pairs with an underscore: EUR_USD.
    instrument: str = "EUR_USD"
    # Candle size. H1 = one hour. Slower timeframes = fewer, calmer trades.
    granularity: str = "H1"

    # --- Strategy (trend following) ---
    fast_ema: int = 12
    slow_ema: int = 26
    trend_ema: int = 200
    rsi_period: int = 14
    atr_period: int = 14
    # Don't buy when RSI is already stretched, don't sell when it's washed out.
    rsi_long_range: tuple = (40.0, 70.0)
    rsi_short_range: tuple = (30.0, 60.0)
    # Stop-loss / take-profit as multiples of ATR (average bar size).
    # 1.5 / 3.0 means every winner is worth twice every loser.
    sl_atr: float = 1.5
    tp_atr: float = 3.0
    # Close a trade that's gone nowhere after this many candles.
    max_hold_bars: int = 48

    # --- AI filter ---
    use_ai_filter: bool = True
    # Only take a trade if the model rates its win chance at least this high.
    # With a 2:1 reward/risk, anything above ~0.34 is break-even before costs.
    ai_threshold: float = 0.40
    # Need this many finished past trades before the model is trusted.
    ai_min_train: int = 30
    ai_retrain_every: int = 10

    # --- Risk ---
    # Fraction of the account lost if a trade hits its stop. 0.01 = 1%.
    risk_per_trade: float = 0.01
    # Stop opening new trades for the day after losing this much. 0.03 = 3%.
    max_daily_loss: float = 0.03
    max_open_trades: int = 1
    # Hard cap on position size relative to account size.
    max_leverage: float = 10.0

    # --- Backtest costs ---
    spread_pips: float = 1.2

    # --- Live ---
    history_bars: int = 3000
    poll_seconds: int = 60
    # Real-money trading is refused unless this is explicitly turned on.
    allow_live: bool = False

    oanda_token: str = field(default="", repr=False)
    oanda_account_id: str = ""
    oanda_env: str = "practice"

    @property
    def pip_size(self) -> float:
        return 0.01 if self.instrument.endswith("_JPY") else 0.0001

    def validate(self) -> None:
        parts = self.instrument.split("_")
        if len(parts) != 2 or ACCOUNT_CURRENCY not in parts:
            raise ValueError(
                f"instrument {self.instrument!r} not supported: use a pair "
                f"with {ACCOUNT_CURRENCY} on one side, written like EUR_USD"
            )
        if not 0 < self.risk_per_trade <= 0.05:
            raise ValueError("risk_per_trade must be between 0 and 0.05 (5%)")
        if not 0 < self.max_daily_loss <= 0.2:
            raise ValueError("max_daily_loss must be between 0 and 0.2 (20%)")
        if self.oanda_env not in ("practice", "live"):
            raise ValueError("OANDA_ENV must be 'practice' or 'live'")


def load_settings() -> Settings:
    """Build Settings from environment variables (and .env if present)."""
    env = os.environ
    s = Settings()
    s.instrument = env.get("FOREX_INSTRUMENT", s.instrument).strip().upper()
    s.granularity = env.get("FOREX_GRANULARITY", s.granularity).strip().upper()
    if env.get("FOREX_RISK_PER_TRADE"):
        s.risk_per_trade = float(env["FOREX_RISK_PER_TRADE"])
    if env.get("FOREX_MAX_DAILY_LOSS"):
        s.max_daily_loss = float(env["FOREX_MAX_DAILY_LOSS"])
    if env.get("FOREX_USE_AI"):
        s.use_ai_filter = env["FOREX_USE_AI"].strip().lower() not in ("0", "no", "false")
    s.allow_live = env.get("FOREX_ALLOW_LIVE", "").strip().lower() == "yes"
    s.oanda_token = env.get("OANDA_API_TOKEN", "").strip()
    s.oanda_account_id = env.get("OANDA_ACCOUNT_ID", "").strip()
    s.oanda_env = env.get("OANDA_ENV", "practice").strip().lower() or "practice"
    s.validate()
    return s
