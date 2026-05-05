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
import signal
import multiprocessing
import os
import threading
from hypercorn.config import Config
from hypercorn.asyncio import serve
from backend.streamer import MarketDataStreamer
from backend.simulator import TradingSimulator
from backend.book import Book
from backend.server import create_server, update_prices
from config import WEBSOCKET_HOST, WEBSOCKET_PORT, DASHBOARD_PORT


def _run_dashboard():
    """
    Runs the Plotly Dash dashboard in a completely separate process.
    Isolated from the main process so Flask's signal handling
    cannot interfere with our Ctrl+C handler.

    Stderr is suppressed for the first 3 seconds to hide the cosmetic
    startup race condition errors caused by the browser firing interval
    requests before callbacks finish registering in the spawned process.
    """
    import sys
    import time

    # Suppress stderr for 3 seconds to hide Dash startup race errors
    _real_stderr = sys.stderr
    sys.stderr = open(os.devnull, 'w')

    def _restore():
        time.sleep(3)
        sys.stderr = _real_stderr

    threading.Thread(target=_restore, daemon=True).start()

    from frontend.dashboard import create_dashboard
    dashboard = create_dashboard()
    print(f"[Main] Starting dashboard on http://localhost:{DASHBOARD_PORT}")
    dashboard.run(
        host="localhost",
        port=DASHBOARD_PORT,
        debug=False,
        use_reloader=False,
    )


async def _run_backend(book: Book, shutdown_trigger, shutdown_event: asyncio.Event):
    """
    Runs the streamer, simulator and WebSocket server
    as concurrent async tasks.
    """
    price_queue = asyncio.Queue()

    streamer = MarketDataStreamer(price_queue)
    simulator = TradingSimulator(book, price_queue, stop_event=shutdown_event)
    quart_app = create_server(book)

    config = Config()
    config.bind = [f"{WEBSOCKET_HOST}:{WEBSOCKET_PORT}"]
    config.loglevel = "warning"

    print(f"[Main] Starting WebSocket server on ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")

    async def _streamer_with_server_update():
        queue_copy = asyncio.Queue()

        async def _forward():
            while not shutdown_event.is_set():
                try:
                    prices = await asyncio.wait_for(
                        price_queue.get(), timeout=1.0
                    )
                    await update_prices(prices)
                    await queue_copy.put(prices)
                except asyncio.TimeoutError:
                    continue

        simulator.price_queue = queue_copy

        await asyncio.gather(
            streamer.stream(),
            _forward(),
        )

    await asyncio.gather(
        _streamer_with_server_update(),
        simulator.run(),
        serve(quart_app, config, shutdown_trigger=shutdown_trigger),
    )


def main():
    """
    Application entry point.
    """
    multiprocessing.freeze_support()

    print("[Main] Starting Finalto Risk Management Dashboard")
    print(f"[Main] Dashboard will be available at http://localhost:{DASHBOARD_PORT}")
    print("[Main] Press Ctrl+C to stop")

    book = Book()

    dashboard_process = multiprocessing.Process(
        target=_run_dashboard,
        daemon=True,
    )
    dashboard_process.start()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    shutdown_event = asyncio.Event()

    def _signal_handler(signum, frame):
        print("\n[Main] Shutting down gracefully...")
        loop.call_soon_threadsafe(shutdown_event.set)
        threading.Timer(2.0, lambda: os._exit(0)).start()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        loop.run_until_complete(
            _run_backend(book, shutdown_event.wait, shutdown_event)
        )
    except KeyboardInterrupt:
        print("\n[Main] Shutting down gracefully...")
    finally:
        loop.close()
        dashboard_process.terminate()
        dashboard_process.join(timeout=3)
        os._exit(0)


if __name__ == "__main__":
    main()