"""
WebSocket server for the Finalto risk management dashboard.

Built with Quart (async Flask), this server:
- Accepts WebSocket connections from the dashboard
- Broadcasts real time price updates and book state every second
- Handles multiple concurrent dashboard connections gracefully

Quart is chosen over Flask because it natively supports async/await
and WebSockets, which are required for real time data streaming.
"""

import asyncio
import json
from quart import Quart, websocket
from backend.book import Book
from backend.models import Price
from config import WEBSOCKET_PORT, DASHBOARD_UPDATE_INTERVAL

app = Quart(__name__)

# Track all connected dashboard clients
connected_clients: set = set()


def _serialise_prices(prices: dict[str, Price]) -> dict:
    """
    Convert Price models to JSON serialisable dictionaries.

    Args:
        prices: Dictionary of instrument -> Price model.

    Returns:
        Dictionary safe to serialise with json.dumps.
    """
    return {
        instrument: {
            "bid": float(price.bid),
            "ask": float(price.ask),
            "mid": float(price.mid),
            "spread": float(price.spread),
            "timestamp": price.timestamp.isoformat(),
        }
        for instrument, price in prices.items()
    }


def _serialise_book_state(book: Book) -> dict:
    """
    Convert current book state to JSON serialisable dictionary.

    Args:
        book: The Book instance with current positions and PnL.

    Returns:
        Dictionary safe to serialise with json.dumps.
    """
    state = book.get_current_state()

    return {
        "positions": {
            instrument: {
                "net_size": float(pos.net_size),
                "avg_entry_price": float(pos.avg_entry_price),
                "unrealised_pnl": float(pos.unrealised_pnl),
                "realised_pnl": float(pos.realised_pnl),
                "total_pnl": float(pos.unrealised_pnl + pos.realised_pnl),
            }
            for instrument, pos in state.positions.items()
        },
        "client_yield": {k: float(v) for k, v in state.client_yield.items()},
        "total_unrealised_pnl": float(state.total_unrealised_pnl),
        "total_realised_pnl": float(state.total_realised_pnl),
        "total_pnl": float(state.total_unrealised_pnl + state.total_realised_pnl),
        "total_spread_revenue": float(state.total_spread_revenue),
        "timestamp": state.timestamp.isoformat(),
        "pnl_history": [
            {
                "timestamp": s.timestamp.isoformat(),
                "total_pnl": float(s.total_pnl),
                "total_spread_revenue": float(s.total_spread_revenue),
            }
            for s in book.history
        ],
    }


async def _broadcast_loop():
    """
    Runs forever, pushing snapshots to all connected clients every interval.
    Runs as a background task — completely separate from the connection handler.
    """
    global connected_clients
    interval = DASHBOARD_UPDATE_INTERVAL / 1000

    while True:
        await asyncio.sleep(interval)

        if not connected_clients:
            continue

        try:
            prices = app.current_prices
            if not prices:
                continue

            message = json.dumps({
                "type": "update",
                "prices": _serialise_prices(prices),
                "book": _serialise_book_state(app.book),
            })
        except Exception as e:
            print(f"[Server] Serialisation error: {e}")
            continue

        dead = set()
        for client in list(connected_clients):
            try:
                await client.send(message)
            except Exception:
                dead.add(client)

        connected_clients -= dead


@app.before_serving
async def _start_broadcast():
    """Start the broadcast loop as a background task when the server starts."""
    app.broadcast_task = asyncio.ensure_future(_broadcast_loop())


@app.after_serving
async def _stop_broadcast():
    """Cancel the broadcast task cleanly on shutdown."""
    task = getattr(app, "broadcast_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@app.websocket("/ws")
async def ws():
    """
    WebSocket endpoint. Registers the client and parks until disconnection.
    All sending happens in the broadcast loop — not here.
    This means no exception in sending can ever cause a 1011.
    """
    client = websocket._get_current_object()
    connected_clients.add(client)
    print(f"[Server] Dashboard connected. Total connections: {len(connected_clients)}")

    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        connected_clients.discard(client)
        print(f"[Server] Dashboard disconnected. Total connections: {len(connected_clients)}")


def create_server(book: Book) -> Quart:
    """
    Attach the book instance to the Quart app and return it.

    Args:
        book: The shared Book instance.

    Returns:
        Configured Quart app ready to run.
    """
    app.book = book
    app.current_prices = {}
    return app


async def update_prices(prices: dict[str, Price]) -> None:
    """
    Update the server's current price snapshot.

    Called by the streamer whenever new prices are generated.

    Args:
        prices: Latest prices for all instruments.
    """
    app.current_prices = prices