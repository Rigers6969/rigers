"""AI-assisted forex trading bot.

Trend-following rules generate trade ideas, a machine-learning filter
(trained only on past, already-finished trades) decides which ones to take,
and a risk manager sizes every position so a single loss is small.

Runs against an OANDA practice (demo, fake-money) account by default.
See forex_bot/README.md for the beginner walkthrough.
"""
