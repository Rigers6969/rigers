"""Minimal OANDA v20 REST client - just what the bot needs.

Docs: https://developer.oanda.com/rest-live-v20/introduction/
"practice" talks to the demo (fake money) server, "live" to real money.
"""
from typing import Optional

import pandas as pd
import requests

URLS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}
MAX_CANDLES_PER_REQUEST = 5000


class OandaError(RuntimeError):
    pass


class OandaClient:
    def __init__(self, token: str, account_id: str, env: str = "practice",
                 session: Optional[requests.Session] = None, timeout: float = 20.0):
        if not token:
            raise OandaError("OANDA_API_TOKEN is not set - see forex_bot/README.md step 2")
        if env not in URLS:
            raise OandaError(f"unknown OANDA env {env!r}")
        self.env = env
        self.account_id = account_id
        self.base = URLS[env]
        self.timeout = timeout
        self.http = session or requests.Session()
        self.http.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept-Datetime-Format": "RFC3339",
        })
        self._precision = {}

    def _request(self, method: str, path: str, **kwargs) -> dict:
        resp = self.http.request(method, self.base + path, timeout=self.timeout, **kwargs)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("errorMessage", resp.text)
            except ValueError:
                detail = resp.text
            raise OandaError(f"{method} {path} -> HTTP {resp.status_code}: {detail}")
        return resp.json()

    def _require_account(self) -> str:
        if not self.account_id:
            raise OandaError("OANDA_ACCOUNT_ID is not set - see forex_bot/README.md step 2")
        return self.account_id

    # --- market data ---

    def candles(self, instrument: str, granularity: str = "H1", count: int = 500,
                to: Optional[str] = None, include_incomplete: bool = False) -> pd.DataFrame:
        params = {"granularity": granularity, "price": "M", "count": min(count, MAX_CANDLES_PER_REQUEST)}
        if to:
            params["to"] = to
        data = self._request("GET", f"/v3/instruments/{instrument}/candles", params=params)
        rows = [
            {
                "time": c["time"],
                "open": float(c["mid"]["o"]), "high": float(c["mid"]["h"]),
                "low": float(c["mid"]["l"]), "close": float(c["mid"]["c"]),
                "complete": bool(c.get("complete", True)),
            }
            for c in data.get("candles", [])
        ]
        df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "complete"])
        df.index = pd.to_datetime(df.pop("time"), utc=True)
        if not include_incomplete:
            df = df[df["complete"]]
        return df.drop(columns="complete")

    def candles_history(self, instrument: str, granularity: str, total: int) -> pd.DataFrame:
        """Up to `total` most recent complete candles, paging back 5000 at a time."""
        frames, to = [], None
        remaining = total
        while remaining > 0:
            chunk = self.candles(instrument, granularity, min(remaining, MAX_CANDLES_PER_REQUEST), to=to)
            if chunk.empty:
                break
            frames.append(chunk)
            remaining -= len(chunk)
            to = chunk.index[0].strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            if len(chunk) < MAX_CANDLES_PER_REQUEST:
                break
        if not frames:
            return pd.DataFrame(columns=["open", "high", "low", "close"])
        df = pd.concat(frames).sort_index()
        return df[~df.index.duplicated(keep="last")].tail(total)

    # --- account ---

    def account_summary(self) -> dict:
        return self._request("GET", f"/v3/accounts/{self._require_account()}/summary")["account"]

    def open_trades(self, instrument: Optional[str] = None) -> list:
        trades = self._request("GET", f"/v3/accounts/{self._require_account()}/openTrades")["trades"]
        return [t for t in trades if instrument is None or t["instrument"] == instrument]

    def price_precision(self, instrument: str) -> int:
        if instrument not in self._precision:
            data = self._request("GET", f"/v3/accounts/{self._require_account()}/instruments",
                                 params={"instruments": instrument})
            self._precision[instrument] = int(data["instruments"][0]["displayPrecision"])
        return self._precision[instrument]

    # --- orders ---

    def market_order(self, instrument: str, units: int, stop_distance: float,
                     take_profit_distance: float) -> dict:
        """Market order with stop-loss and take-profit attached on fill.

        Distances (not prices) are used so the levels are measured from the
        actual fill price. Positive units = buy, negative = sell.
        """
        if units == 0:
            raise OandaError("refusing to send a 0-unit order")
        p = self.price_precision(instrument)
        order = {
            "order": {
                "type": "MARKET",
                "instrument": instrument,
                "units": str(int(units)),
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
                "stopLossOnFill": {"distance": f"{stop_distance:.{p}f}", "timeInForce": "GTC"},
                "takeProfitOnFill": {"distance": f"{take_profit_distance:.{p}f}", "timeInForce": "GTC"},
            }
        }
        resp = self._request("POST", f"/v3/accounts/{self._require_account()}/orders", json=order)
        if "orderCancelTransaction" in resp:
            reason = resp["orderCancelTransaction"].get("reason", "unknown")
            raise OandaError(f"order was cancelled by OANDA: {reason}")
        return resp

    def close_trade(self, trade_id: str) -> dict:
        return self._request("PUT", f"/v3/accounts/{self._require_account()}/trades/{trade_id}/close")
