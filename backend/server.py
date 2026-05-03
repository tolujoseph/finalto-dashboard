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
            "bid": price.bid,
            "ask": price.ask,
            "mid": price.mid,
            "spread": price.spread,
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
                "net_size": pos.net_size,
                "avg_entry_price": pos.avg_entry_price,
                "unrealised_pnl": pos.unrealised_pnl,
                "realised_pnl": pos.realised_pnl,
                "total_pnl": pos.total_pnl,
            }
            for instrument, pos in state.positions.items()
        },
        "client_yield": state.client_yield,
        "total_unrealised_pnl": state.total_unrealised_pnl,
        "total_realised_pnl": state.total_realised_pnl,
        "total_pnl": state.total_pnl,
        "total_spread_revenue": state.total_spread_revenue,
        "timestamp": state.timestamp.isoformat(),
        "pnl_history": [
            {
                "timestamp": s.timestamp.isoformat(),
                "total_pnl": s.total_pnl,
                "total_spread_revenue": s.total_spread_revenue,
            }
            for s in book.history
        ],
    }


@app.websocket("/ws")
async def ws():
    """
    WebSocket endpoint that streams live data to the dashboard.

    On connection:
    - Registers the client
    - Sends price and book state updates every second
    - Handles disconnection gracefully without crashing

    The dashboard connects here and receives a continuous stream
    of JSON messages containing prices and book state.
    """
    # Register this connection
    connected_clients.add(websocket._get_current_object())
    print(f"[Server] Dashboard connected. Total connections: {len(connected_clients)}")

    try:
        while True:
            # Build the message payload
            book = app.book
            prices = app.current_prices

            if prices:
                message = json.dumps({
                    "type": "update",
                    "prices": _serialise_prices(prices),
                    "book": _serialise_book_state(book),
                })
                await websocket.send(message)

            # Wait before next update
            await asyncio.sleep(DASHBOARD_UPDATE_INTERVAL / 1000)

    except asyncio.CancelledError:
        pass
    finally:
        # Always clean up on disconnect — prevents memory leak
        connected_clients.discard(websocket._get_current_object())
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