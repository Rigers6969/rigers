"""Command line entry point.

  python -m forex_bot demo                       try it now, fake data, no account
  python -m forex_bot check                      test your OANDA connection
  python -m forex_bot backtest                   test the strategy on real history
  python -m forex_bot backtest --csv file.csv    ...or on your own CSV
  python -m forex_bot run --dry-run              live loop, logs trades but sends none
  python -m forex_bot run                        live loop on your practice account
"""
import argparse
import sys
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    # .env sits next to the forex_bot folder (the repo root, or the unzipped folder).
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from .backtest import format_stats, run_backtest
from .broker import OandaClient, OandaError
from .config import load_settings
from .data import load_csv, synthetic_candles


def _client(s):
    return OandaClient(s.oanda_token, s.oanda_account_id, s.oanda_env)


def _compare(candles, s) -> None:
    base = run_backtest(candles, s, use_ai=False).stats()
    print(format_stats("Rules only", base))
    print()
    ai = run_backtest(candles, s, use_ai=True).stats()
    print(format_stats("Rules + AI filter", ai))
    print()
    if base["trades"] < 30:
        print("Note: fewer than 30 trades - too few to judge anything. Use more history.")
    print("Reminder: backtests are optimistic. Paper-trade for weeks before risking real money.")


def cmd_demo(s, args) -> None:
    print("DEMO on SYNTHETIC (made-up) prices - this shows the bot works, it says")
    print("nothing about whether it would make money on the real market.\n")
    _compare(synthetic_candles(args.bars, seed=args.seed), s)


def cmd_backtest(s, args) -> None:
    if args.csv:
        candles = load_csv(args.csv)
        src = args.csv
    else:
        candles = _client(s).candles_history(s.instrument, s.granularity, args.bars)
        src = f"OANDA {s.oanda_env}"
    if candles.empty:
        sys.exit("No candles returned.")
    print(f"{s.instrument} {s.granularity}: {len(candles)} candles from {src}, "
          f"{candles.index[0]:%Y-%m-%d} to {candles.index[-1]:%Y-%m-%d}\n")
    _compare(candles, s)


def cmd_check(s, args) -> None:
    c = _client(s)
    acct = c.account_summary()
    print(f"Connected to OANDA {c.env.upper()} account {acct['id']}")
    print(f"  balance {acct['balance']} {acct['currency']}, NAV {acct['NAV']}, open trades {acct['openTradeCount']}")
    last = c.candles(s.instrument, s.granularity, 1)
    if not last.empty:
        print(f"  latest {s.instrument} {s.granularity} close: {last['close'].iloc[-1]}")
    print("All good.")


def cmd_run(s, args) -> None:
    from .live import LiveTrader
    LiveTrader(_client(s), s, dry_run=args.dry_run).run_forever()


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m forex_bot", description="AI-assisted forex bot")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="backtest on synthetic prices (no account needed)")
    d.add_argument("--bars", type=int, default=8000)
    d.add_argument("--seed", type=int, default=7)
    b = sub.add_parser("backtest", help="backtest on OANDA history or a CSV")
    b.add_argument("--bars", type=int, default=20000)
    b.add_argument("--csv", help="use a CSV file instead of OANDA")
    sub.add_parser("check", help="test the OANDA connection")
    r = sub.add_parser("run", help="run the live trading loop")
    r.add_argument("--dry-run", action="store_true", help="decide trades but don't send orders")
    args = p.parse_args(argv)

    try:
        s = load_settings()
        {"demo": cmd_demo, "backtest": cmd_backtest, "check": cmd_check, "run": cmd_run}[args.cmd](s, args)
    except (OandaError, ValueError) as e:
        sys.exit(f"Error: {e}")
    except requests.RequestException as e:
        sys.exit(f"Error: could not reach OANDA - check your internet connection ({type(e).__name__})")
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
