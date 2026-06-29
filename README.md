# Finalto Risk Management Dashboard

A real-time forex market-making risk dashboard. It simulates a liquidity
provider's book: prices stream to a set of mock broker clients, clients
trade against those prices, and the book takes the opposite side of every
trade — tracking net exposure, unrealised/realised PnL, and spread revenue
live in the browser.

The project is built as a fully async Python pipeline (Quart, asyncio,
WebSockets) feeding a Plotly Dash front end, with Pydantic models enforcing
data integrity at every stage and a pytest suite covering the PnL engine's
core business logic.

> Client BUY → Finalto goes short. Client SELL → Finalto goes long.
> Finalto's book is always the mirror image of aggregate client flow.

---

## Architecture

Data flows through the system in a single pipeline:

1. **Market Data Streamer** generates random-walk bid/ask prices for each instrument
2. **asyncio Queue** passes prices to the simulator and the book
3. **Trading Simulator** runs five mock clients, each trading independently at random intervals
4. **Book** processes each trade, tracking net positions and calculating PnL in real time
5. **Quart WebSocket Server** broadcasts a snapshot of the book to connected dashboards every second
6. **Plotly Dash Dashboard** receives snapshots and renders live charts and metrics in the browser

```
MarketDataStreamer ──► asyncio.Queue ──► TradingSimulator ──► Book
                                                                 │
                                                                 ▼
                                              Quart WebSocket Server
                                                                 │
                                                                 ▼
                                                Plotly Dash Dashboard
```

**Components:**

| File | Responsibility |
|---|---|
| `config.py` | Central configuration for instruments, clients and timing |
| `backend/models.py` | Pydantic data models for all data structures |
| `backend/streamer.py` | Async market data streamer using a random walk |
| `backend/simulator.py` | Mock client trading activity simulator |
| `backend/book.py` | Real-time book management and PnL calculation — the core business logic |
| `backend/server.py` | Quart WebSocket server streaming data to the dashboard |
| `frontend/dashboard.py` | Plotly Dash real-time dashboard |

---

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package and project manager)
- Git

### Installing uv

**Mac/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Restart your terminal after installation, then verify:
```bash
uv --version
```

---

## Installation

```bash
git clone https://github.com/tolujoseph/finalto-dashboard.git
cd finalto-dashboard
```

**Create and activate the virtual environment:**

Mac/Linux:
```bash
uv venv
source .venv/bin/activate
```

Windows:
```powershell
uv venv
.venv\Scripts\activate
```

You should see `(finalto-dashboard)` appear at the start of your terminal
prompt, confirming the environment is active.

**Install all dependencies (including dev/test dependencies):**
```bash
uv sync
```

---

## Running the Application

With the virtual environment active:

```bash
python main.py
```

Then open your browser at:

```
http://localhost:8050
```

The dashboard connects automatically over WebSocket and begins displaying
live prices, positions and PnL. Press `Ctrl+C` in the terminal to shut
everything down gracefully.

---

## Testing

The test suite lives in `tests/` and is built with `pytest` (plus
`pytest-asyncio` for the async components). It is organised by backend
module, mirroring the production code:

```bash
uv run pytest          # run the full suite
uv run pytest -v       # verbose, one line per test
uv run pytest -q       # quiet summary
```

81 tests, all passing, run in under two seconds with no external
dependencies (no network, no real event loop sleeps of more than a few
hundred milliseconds).

| File | What it covers |
|---|---|
| `tests/test_book.py` | The PnL engine — position direction flipping, weighted average entry price, realised PnL on partial closes, exact closes and position flips, spread revenue and per-client yield attribution, unrealised PnL on price moves, history bounding (`MAX_HISTORY_POINTS`), and snapshot immutability |
| `tests/test_models.py` | Pydantic model behaviour — required field validation, type coercion, enum handling, default factories (UTC timestamps), and the `total_pnl` computed properties on `Position` and `BookState` |
| `tests/test_streamer.py` | The random-walk price generator (deterministic via monkeypatching `numpy.random.normal`), the price floor that prevents negative prices, bid/ask/spread consistency, and the async streaming loop's queue-publishing and cancellation behaviour |
| `tests/test_simulator.py` | The trading simulator's price listener, BUY→ask / SELL→bid trade construction, and graceful handling of trades attempted before any prices have arrived |

Coverage focuses on `backend/book.py` deliberately — it is the component
where a silent logic error would be most consequential (incorrect PnL),
and the least visually verifiable from the dashboard alone.

### A real bug caught by writing these tests

While writing tests for position flips and exact closes in
`Book.process_trade`, two tests failed in a way that pointed at the
implementation rather than the test:

```python
def test_exact_close_zeroes_net_size_and_realises_full_pnl(self):
    book.process_trade(make_trade(direction=Direction.SELL, size=10_000, price=1.1000))
    book.process_trade(make_trade(direction=Direction.BUY, size=10_000, price=1.2000))
    # Expected ~£10 of realised profit. Got exactly 0.0.
```

The root cause: `process_trade` updated `position.avg_entry_price` to the
new trade price *before* using `avg_entry_price` to calculate realised
PnL on the closed portion. For partial closes this was harmless (the
average entry price isn't touched on a partial close), but for any
**exact close or position flip**, the realised PnL calculation became
`trade.price - trade.price`, which is always zero — silently discarding
real gains and losses on every flip or full close, with no error or
warning anywhere in the system.

The fix: capture `previous_avg_entry_price` before any mutation, use it
for the realised PnL calculation, and only update `avg_entry_price`
afterwards. See `backend/book.py` and the corresponding tests in
`tests/test_book.py::TestRealisedPnl` for the exact scenarios that
caught and now guard against this regression.

This is the kind of bug that is invisible from the dashboard in a short
manual test session — positions and totals still look plausible — but
compounds into materially wrong PnL over a long-running book. It's the
core motivation for testing `book.py` exhaustively rather than relying on
the stress tests in [TESTS.md](TESTS.md) alone.

---

## Stress Testing

Beyond unit tests, the running system has been validated under load —
extended runs, scaled client counts, high-frequency trading, and browser
reconnection. Full methodology and results are documented in
[TESTS.md](TESTS.md).

Key findings:
- Stable memory usage (~116–128 MB) regardless of client count
- CPU usage below 2% even under high-frequency stress conditions
- Scales from 5 to 20+ clients with no code changes — just update `config.py`
- WebSocket reconnects automatically if the browser is closed and reopened

---

## Technology Choices

| Technology | Reason |
|---|---|
| **Quart** | Async Flask replacement with native WebSocket support |
| **Plotly Dash** | Professional interactive dashboards entirely in Python |
| **Pydantic** | Data validation and modelling throughout the pipeline |
| **asyncio** | Concurrent streamer, simulator and server in one process |
| **uv** | Modern, reproducible Python dependency management |
| **websockets** | Real-time bidirectional data push to the dashboard |
| **pytest / pytest-asyncio** | Deterministic testing of both sync business logic and async event-loop code |

---

## Dashboard Metrics

- **Total PnL** — combined unrealised and realised profit/loss across all instruments
- **Unrealised PnL** — open position PnL based on current market prices
- **Realised PnL** — locked-in PnL from closed positions
- **Spread Revenue** — cumulative revenue earned from bid/ask spread on all trades
- **PnL Curve** — real-time chart of total PnL and spread revenue over time
- **Net Positions** — Finalto's current long/short exposure per instrument
- **Client Yield** — spread revenue contribution per client
- **PnL Attribution** — PnL breakdown by instrument
- **Live Prices** — current bid/ask for all instruments, updating every second

---

## Configuration

All configurable parameters live in `config.py`:

```python
# Instruments, clients
INSTRUMENTS = {...}              # forex pairs + XAU/USD, with starting mid prices
CLIENTS = [...]                  # mock broker clients

# Adjust update frequency
PRICE_UPDATE_INTERVAL = 1.0      # seconds between price updates
TRADE_INTERVAL_MIN = 5.0         # minimum seconds between client trades
TRADE_INTERVAL_MAX = 15.0        # maximum seconds between client trades
DASHBOARD_UPDATE_INTERVAL = 1000 # milliseconds between dashboard refreshes

# Control history window
MAX_HISTORY_POINTS = 300         # 5 minutes at 1 update/second

# Trade sizing and volatility
MIN_TRADE_SIZE = 10_000
MAX_TRADE_SIZE = 100_000
VOLATILITY = {...}                # per-instrument random walk volatility
```

---

## Scalability Notes

The application was designed with scalability in mind:

- **Bounded memory** — `MAX_HISTORY_POINTS` caps the history buffer regardless of runtime
- **Async pipeline** — all backend components run concurrently without blocking
- **Throttling** — `DASHBOARD_UPDATE_INTERVAL` controls how frequently the dashboard refreshes, independently of how fast prices generate internally
- **10x scale test** — increasing `CLIENTS` to 50 and `PRICE_UPDATE_INTERVAL` to 0.1s runs stably without dashboard lag, thanks to the WebSocket push architecture

---

## Simulation Details

This is a mock simulation — no real market data is used.

- Prices follow a random walk from realistic starting values
- Mock broker clients trade randomly at configurable intervals
- Finalto takes the opposite side of every client trade (client buys = Finalto short)
- PnL updates in real time as prices move against or in favour of open positions

---

## Stopping the Application

Press `Ctrl+C` in the terminal. Shutdown is graceful: the simulator stops
spawning new trades, the WebSocket server cancels its broadcast loop, and
the dashboard subprocess is terminated cleanly.
