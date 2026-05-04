"""
Main entry point for the Finalto risk management dashboard.

Starts all components concurrently:
- Market data streamer (generates bid/ask prices)
- Trading simulator (generates client trades)
- Quart WebSocket server (streams data to dashboard)
- Plotly Dash dashboard (visualises everything)

Run with:
    python main.py
"""

import asyncio
import threading
from hypercorn.config import Config
from hypercorn.asyncio import serve
from backend.streamer import MarketDataStreamer
from backend.simulator import TradingSimulator
from backend.book import Book
from backend.server import create_server, update_prices
from frontend.dashboard import create_dashboard
from config import WEBSOCKET_HOST, WEBSOCKET_PORT, DASHBOARD_PORT


async def _run_backend(book: Book):
    """
    Runs the streamer, simulator and WebSocket server
    as concurrent async tasks.

    Args:
        book: The shared Book instance.
    """
    # Single queue connecting streamer to simulator and server
    price_queue = asyncio.Queue()

    # Initialise components
    streamer = MarketDataStreamer(price_queue)
    simulator = TradingSimulator(book, price_queue)
    quart_app = create_server(book)

    # Hypercorn config for Quart WebSocket server
    config = Config()
    config.bind = [f"{WEBSOCKET_HOST}:{WEBSOCKET_PORT}"]
    config.loglevel = "warning"

    print(f"[Main] Starting WebSocket server on ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")

    async def _streamer_with_server_update():
        """
        Wraps the streamer to also update the server's
        current prices on every tick.
        """
        queue_copy = asyncio.Queue()

        async def _forward():
            """Forward prices from main queue to server and copy queue."""
            while True:
                prices = await price_queue.get()
                await update_prices(prices)
                await queue_copy.put(prices)

        # Replace simulator's queue reference with copy queue
        simulator.price_queue = queue_copy

        await asyncio.gather(
            streamer.stream(),
            _forward(),
        )

    # Run all backend components concurrently
    await asyncio.gather(
        _streamer_with_server_update(),
        simulator.run(),
        serve(quart_app, config),
    )


def _run_dashboard():
    """
    Runs the Plotly Dash dashboard in a separate thread.

    Dash has its own internal server (Flask based) so it
    runs independently from the async backend.
    """
    dashboard = create_dashboard()
    print(f"[Main] Starting dashboard on http://localhost:{DASHBOARD_PORT}")
    dashboard.run(
        host="localhost",
        port=DASHBOARD_PORT,
        debug=False,
    )


def main():
    """
    Application entry point.
    """
    import traceback
    print("[Main] Starting Finalto Risk Management Dashboard")
    print(f"[Main] Dashboard will be available at http://localhost:{DASHBOARD_PORT}")

    book = Book()

    dashboard_thread = threading.Thread(
        target=_run_dashboard,
        daemon=True,
    )
    dashboard_thread.start()

    try:
        asyncio.run(_run_backend(book))
    except KeyboardInterrupt:
        print("\n[Main] Shutting down gracefully...")
    except Exception as e:
        print(f"[Main] ERROR: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()