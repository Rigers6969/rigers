"""Position sizing and loss limits - the part that keeps a bad run survivable."""
from .config import ACCOUNT_CURRENCY


def quote_to_account(instrument: str, price: float) -> float:
    """How many account-currency dollars one unit of the quote currency is worth."""
    base, quote = instrument.split("_")
    if quote == ACCOUNT_CURRENCY:
        return 1.0
    if base == ACCOUNT_CURRENCY:
        return 1.0 / price
    raise ValueError(f"{instrument}: need {ACCOUNT_CURRENCY} on one side of the pair")


def position_units(balance: float, risk_fraction: float, stop_distance: float,
                   instrument: str, price: float, max_leverage: float) -> int:
    """Units to trade so that hitting the stop loses ~risk_fraction of balance.

    Also capped so the position's total size never exceeds
    balance * max_leverage. Returns 0 if the trade is too small to place.
    """
    if balance <= 0 or stop_distance <= 0 or price <= 0:
        return 0
    conv = quote_to_account(instrument, price)
    units = (balance * risk_fraction) / (stop_distance * conv)
    base = instrument.split("_")[0]
    unit_value = 1.0 if base == ACCOUNT_CURRENCY else price * conv
    units = min(units, balance * max_leverage / unit_value)
    return max(int(units), 0)


def daily_loss_hit(day_start_balance: float, current_balance: float, max_daily_loss: float) -> bool:
    if day_start_balance <= 0:
        return True
    return (day_start_balance - current_balance) / day_start_balance >= max_daily_loss
