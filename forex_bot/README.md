# Forex bot - beginner guide

An automated forex trader. Rules spot trade ideas, a small machine-learning
model ("the AI") learns from past ideas which ones tend to win and vetoes
the rest, and a risk manager keeps each loss to about 1% of the account.

> **Read this first.** Most trading bots lose money, and forex is dominated
> by banks and professional firms. Treat this as a learning project. Use the
> free demo account (fake money) for at least 1-2 months. Only ever risk
> money you could lose entirely without it hurting you.

## Forex in 60 seconds

- You trade **currency pairs**, like **EUR/USD** = how many US dollars one
  euro costs (e.g. 1.0850).
- **Buy** if you think the first currency will rise, **sell** if you think
  it will fall. You can profit either way.
- A **pip** is the smallest normal price step: 0.0001 for most pairs.
- The **spread** is the broker's fee: the small gap between the buy and
  sell price. You pay it on every trade.
- A **stop-loss** automatically closes a losing trade at a set price. A
  **take-profit** closes a winner. This bot always sets both.
- **Leverage** lets you control more money than you have. It multiplies
  losses as much as gains. The bot sizes trades by risk, not by leverage.

## How the bot decides

1. **Trend rule.** Every hour it checks two moving averages (12 and 26
   hours). When the fast one crosses the slow one *in the direction of the
   long-term trend* (200-hour average), that's a trade idea. RSI stops it
   from buying something that has already shot up.
2. **AI filter.** The bot replays every past trade idea to see if it won or
   lost, then trains a logistic-regression model on what the market looked
   like at those moments. New ideas the model rates below a 40% win chance
   are skipped. (Winners are set to be 2x the size of losers, so ~34%+ wins
   is break-even before costs.) It only ever learns from trades that had
   already finished, never from the future.
3. **Risk manager.**
   - Stop-loss at 1.5x the average candle size, take-profit at 3x.
   - Position sized so hitting the stop loses ~1% of the account.
   - Only one trade at a time.
   - Stops opening trades for the day after losing 3%.
   - Stop and target are held by OANDA's servers, so trades stay protected
     even if your computer crashes.

## Step 1 - Install

You need Python 3.10+. From the repo folder:

```bash
pip install -r requirements.txt
```

Try it right away with made-up prices (no account needed):

```bash
python -m forex_bot demo
```

That shows the bot works. It says nothing about real profits.

## Step 2 - Free OANDA demo account

1. Go to **oanda.com** and sign up for a **demo / practice account**. It's
   free and comes with virtual money. (OANDA isn't available in every
   country. If it's not available in yours, tell Claude which country
   you're in and the bot can be adapted to another broker.)
2. Log in. Under **Manage API Access** (in your profile / "My Services"),
   **generate a personal access token**. Copy it.
3. Find your **account ID**. It looks like `101-004-1234567-001` and is
   shown in the account list or in the trading platform.
4. Copy `.env.example` to `.env` (in the repo root) and fill in:
   ```
   OANDA_API_TOKEN=paste-your-token
   OANDA_ACCOUNT_ID=101-004-1234567-001
   OANDA_ENV=practice
   ```
   `.env` is never committed, so your token stays on your machine. Treat
   the token like a password.
5. Test the connection:
   ```bash
   python -m forex_bot check
   ```

## Step 3 - Backtest on real history

```bash
python -m forex_bot backtest            # last 20,000 hourly candles (~3 years)
```

It prints results with and without the AI filter. What to look at:

| Number | Meaning | Healthy |
|---|---|---|
| trades taken | how many trades | 100+ to mean anything |
| profit factor | money won ÷ money lost | above 1.3 |
| max drawdown | worst drop from a peak | under 20% |
| avg trade (R) | average result per trade, in units of risk | above +0.1R |

If the numbers are poor, **don't trade it**. Try another pair
(`FOREX_INSTRUMENT=GBP_USD`) or timeframe (`FOREX_GRANULARITY=H4`) in
`.env`. Be careful, though: trying dozens of combinations until one looks
good is how people fool themselves ("overfitting").

## Step 4 - Paper trade on the demo account

```bash
python -m forex_bot run --dry-run   # decides trades, logs them, sends nothing
python -m forex_bot run             # places real orders on the DEMO account
```

Leave it running (a spare computer or a cheap cloud server works). Every
decision is printed. Trades are logged to `forex_bot/journal.csv`, and you
can watch them in OANDA's app too.

**Emergency stop:** create an empty file named `STOP` inside the
`forex_bot` folder. The bot stops opening trades until you delete it. Close
any open trade from the OANDA app. Ctrl+C quits the bot.

## Step 5 - Real money (only if the demo worked)

Only after 1-2+ months of demo results you're happy with:
1. Open a live OANDA account and fund it with a **small** amount.
2. Make a live API token, then set `OANDA_ENV=live` **and**
   `FOREX_ALLOW_LIVE=yes`. The bot refuses to trade real money without both.
3. Keep `FOREX_RISK_PER_TRADE` at 0.01 or lower.

Check your local rules on taxes and on leveraged trading before you start.

## Files

| File | What it does |
|---|---|
| `config.py` | all settings and their defaults |
| `indicators.py` | moving averages, RSI, ATR |
| `strategy.py` | trade rules and trade simulator |
| `ai_filter.py` | the machine-learning veto model |
| `risk.py` | position sizing and loss limits |
| `backtest.py` | historical testing |
| `broker.py` | talks to OANDA |
| `live.py` | the live trading loop and its safety checks |
| `data.py` | CSV loading and synthetic demo data |

Tests: `python -m unittest tests.test_forex_bot`
