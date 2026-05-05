# Stress Testing & Validation

This document records the testing performed on the Finalto Risk Management Dashboard
to validate stability, performance and correctness under various conditions.

---

## Baseline Test — 5 Clients, Default Config

**Configuration:**
- 5 clients
- Trade interval: 5–15 seconds
- Dashboard refresh: 1000ms
- Price update: 1.0 seconds
- Max trade size: 100,000 units

**Results:**
- System ran stably for 10+ minutes with no crashes
- Memory usage: ~128 MB across 3 Python processes
- CPU usage: ~1.6% at rest between trades
- Dashboard updated smoothly in real time
- Ctrl+C shut down all components cleanly within 2 seconds
- WebSocket reconnected automatically when browser was closed and reopened

---

## Client Scale Test — 11 Clients

**Configuration:**
- 11 clients (added: Ragnarok Securities, Eternal Investments, Ascendant Trading,
  Dominion Brokers, Supreme Capital, Olympus Trading)
- All other settings unchanged from baseline

**Results:**
- Memory usage: ~118 MB — lower than the 5 client baseline
- CPU usage: ~0.8%
- No degradation in dashboard update speed
- All 11 clients visible and updating in the Client Yield chart
- System remained stable throughout

---

## Stress Test — 20 Clients, High Frequency Trading

**Configuration:**
- 20 clients
- Trade interval: 0.5–2.0 seconds (10x faster than baseline)
- Dashboard refresh: 500ms (2x faster)
- Price update: 0.5 seconds (2x faster)
- Max trade size: 500,000 units (5x larger)
- Volatility: 2–3x baseline on all instruments

**Results:**
- Memory usage: ~116 MB — lower than both previous tests
- CPU usage: ~0.4% — lower than baseline
- All 20 clients visible and updating in the Client Yield chart
- Net positions showing large swings up to ±4M from bigger trade sizes
- XAUUSD showing significant PnL attribution from higher volatility
- Live prices updating smoothly with increased volatility clearly visible
- Dashboard remained fully responsive throughout
- No crashes, no memory growth, no WebSocket errors

**Key finding:** Memory and CPU usage decreased as client count increased,
demonstrating that asyncio handles concurrent tasks with minimal overhead —
there is no threading cost per client, just a single event loop scheduling
all tasks efficiently.

---

## Reconnection Test

**Configuration:**
- Default config (5 clients)
- Browser closed and reopened mid-session

**Results:**
- Dashboard reconnected automatically within 2 seconds
- No data loss — book state and history fully preserved
- WebSocket re-established cleanly with no errors
- PnL history chart continued from where it left off

---

## Notes on Scalability

The system is designed to scale easily via `config.py`. Key levers:

- **`CLIENTS`** — add any number of mock clients, each runs as an independent asyncio task
- **`TRADE_INTERVAL_MIN/MAX`** — controls trading frequency per client
- **`PRICE_UPDATE_INTERVAL`** — controls how often the streamer generates new prices
- **`DASHBOARD_UPDATE_INTERVAL`** — controls WebSocket broadcast frequency
- **`MAX_HISTORY_POINTS`** — caps memory usage for the PnL history chart
- **`VOLATILITY`** — controls price movement per instrument per tick
- **`MAX_TRADE_SIZE`** — controls the scale of position risk on the book

At 20 clients trading every 0.5–2 seconds, the asyncio event loop handled all
concurrent tasks without issue, keeping memory stable at 116 MB and CPU below 1%.