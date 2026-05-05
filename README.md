# Finalto Risk Management Dashboard

An MVP risk management dashboard visualizing most important metrics for book management such as PnL curve, monetization, client yield and PnL attribution.
Prices are shown to a set of clients and a simulation of the clients' trading activities utilizing the bid/ask prices and their implications to our book and designed such that if the client buys, we are short and if the client sells, we are long.


---

## Architecture

Data flows through the system in a single pipeline:

1. **Market Data Streamer** generates a random walk bid/ask prices for each instrument
2. **asyncio Queue** passes prices to the simulator and book
3. **Trading Simulator** runs five mock clients, each trading independently at random intervals
4. **Book** processes each trade, tracking net positions and calculating PnL in real time
5. **Quart WebSocket Server** broadcasts a snapshot of the book to connected dashboards every second
6. **Plotly Dash Dashboard** receives snapshots and renders live charts and metrics in the browser

**Components:**
- `config.py` — central configuration for instruments, clients and timing
- `backend/models.py` — Pydantic data models for all data structures
- `backend/streamer.py` — async market data streamer using random walk
- `backend/simulator.py` — mock client trading activity simulator
- `backend/book.py` — real-time book management and PnL calculation
- `backend/server.py` — Quart WebSocket server streaming data to dashboard
- `frontend/dashboard.py` — Plotly Dash real-time dashboard


## Testing & Stress Testing

Experiments have been carried out under a range of conditions including extended
runs, scaled client counts, high frequency trading, and browser reconnection.

Full test results and methodology are documented in [TESTS.md](TESTS.md).

Key findings:
- Stable memory usage (~116–128 MB) regardless of client count
- CPU usage below 2% even under high frequency stress conditions
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
| **uv** | Modern reproducible Python dependency management |
| **websockets** | Real-time bidirectional data push to the dashboard |

---

## Prerequisites

- Python 3.11+
- uv (Python package manager)
- Git

## Installing uv

**Windows:**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Restart your terminal after installation, then verify:
```bash
uv --version
```

**Mac/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart your terminal after installation.

---

## Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/finalto-dashboard.git
cd finalto-dashboard

# Install all dependencies
uv sync

# Activate the virtual environment
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate
```

---

## Running the Application

```bash
python main.py
```

Then open your browser at:
http://localhost:8050

The dashboard will connect automatically and begin displaying live data.

---

## Dashboard Metrics

- **Total PnL** — combined unrealised and realised profit/loss across all instruments
- **Unrealised PnL** — open position PnL based on current market prices
- **Realised PnL** — locked-in PnL from closed positions
- **Spread Revenue** — cummulative revenue earned from bid/ask spread on all trades
- **PnL Curve** — real-time chart of total PnL and spread revenue over time
- **Net Positions** — Finalto's current long/short exposure per instrument
- **Client Yield** — spread revenue contribution per client
- **PnL Attribution** — PnL breakdown by instrument
- **Live Prices** — current bid/ask for all instruments updating every second

---

## Configuration

All configurable parameters live in `config.py`:

```python
# Scale up clients to stress test
CLIENTS = ["ClientA", "ClientB", ...]  # add more clients

# Adjust update frequency
PRICE_UPDATE_INTERVAL = 1.0      # seconds between price updates
TRADE_INTERVAL_MIN = 5.0         # minimum seconds between trades
TRADE_INTERVAL_MAX = 15.0        # maximum seconds between trades

# Control history window
MAX_HISTORY_POINTS = 300         # 5 minutes at 1 update/second
```

---

## Scalability Notes

The application was designed with scalability in mind:

- **Bounded memory** — `MAX_HISTORY_POINTS` caps the history buffer regardless of runtime
- **Async pipeline** — all backend components run concurrently without blocking
- **Throttling** — `DASHBOARD_UPDATE_INTERVAL` controls how frequently the dashboard refreshes independently of how fast prices generate internally
- **10x scale test** — increasing `CLIENTS` to 50 and `PRICE_UPDATE_INTERVAL` to 0.1s runs stably without dashboard lag due to the WebSocket push architecture

---

## Simulation Details

This is a mock simulation — no real market data is used.

- Prices follow a random walk from realistic starting values
- 5 mock broker clients trade randomly at configurable intervals
- Finalto takes the opposite side of every client trade (client buys = Finalto short)
- PnL updates in real time as prices move against or in favour of open positions

---

## Stopping the Application

Press `Ctrl+C` in the terminal.