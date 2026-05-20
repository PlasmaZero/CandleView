# CandleView

A modular day trading strategy engine for equities and options.

## Features

- **Data Layer** — Real-time and historical OHLCV from Yahoo Finance, options chains via yfinance or Tradier, plus EMA, RSI, VWAP, Bollinger Bands, ATR, MACD, and Volume Profile indicators.
- **Strategy Engine** — Pluggable strategies including Momentum Breakout and Options Flow, with market-hour, volume, and earnings-date filters.
- **Execution Layer** — Unified broker interface supporting Alpaca (equities + options paper/live) and Tradier, with order management and stop-loss tracking.
- **Risk Management** — Configurable per-trade risk, daily loss auto-shutoff, Kelly Criterion and fixed-fractional position sizing.
- **Dashboard & Logging** — Terminal dashboard via `rich`, optional FastAPI web layer, SQLite + CSV trade journal.

## Quick start

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml   # edit with your API keys and tickers
python -m candleview.main --mode paper --dashboard terminal
```

## Configuration

Edit `config.yaml` to set:
- `tickers` — symbols to scan
- `risk.max_risk_per_trade_pct` — default 1.0%
- `risk.max_daily_loss_pct` — default 3.0%
- `broker.name` — `alpaca` or `tradier`
- `broker.paper` — true/false

Set environment variables for credentials:
- `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`
- `TRADIER_TOKEN`, `TRADIER_ACCOUNT_ID`

## Project layout

```
candleview/
  data/         OHLCV, options chains, indicators
  strategies/   Momentum Breakout, Options Flow
  execution/    Broker adapters and order management
  risk/         Risk manager and position sizing
  filters/      Market hours, earnings, volume filters
  storage/      SQLite + CSV trade journal
  dashboard/    Terminal and web dashboards
```

## Disclaimer

For educational and research use. Trading involves substantial risk of loss. Always test with paper trading before deploying real capital.
