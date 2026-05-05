"""
Trading activity simulator for the Finalto risk management dashboard.

Simulates a set of mock clients sending buy/sell orders to Finalto
based on current market prices. Each client trades independently
at random intervals with random sizes and instruments.

This mimics real broker clients trading with Finalto as their
liquidity provider.
"""

import asyncio
import random
from backend.models import Trade, Direction
from backend.book import Book
from config import (
    CLIENTS,
    INSTRUMENTS,
    MIN_TRADE_SIZE,
    MAX_TRADE_SIZE,
    TRADE_SIZE_STEP,
    TRADE_INTERVAL_MIN,
    TRADE_INTERVAL_MAX,
)


class TradingSimulator:
    """
    Simulates trading activity from multiple mock clients.

    Each client runs as an independent async task, randomly
    deciding when to trade, which instrument to trade, and
    in which direction.
    """

    def __init__(self, book: Book, price_queue: asyncio.Queue,
                 stop_event: asyncio.Event | None = None):
        """
        Args:
            book: The Book instance to send trades to.
            price_queue: Queue to read current prices from.
            stop_event: Optional event that signals graceful shutdown.
        """
        self.book = book
        self.price_queue = price_queue
        self.stop_event = stop_event or asyncio.Event()
        self.current_prices = {}

    async def _price_listener(self):
        """
        Listens to the price queue and updates current prices.

        Runs as a background task so all client simulators
        always have access to the latest prices.
        """
        while not self.stop_event.is_set():
            try:
                prices = await asyncio.wait_for(
                    self.price_queue.get(), timeout=1.0
                )
                self.current_prices = prices
                self.book.update_prices(prices)
            except asyncio.TimeoutError:
                continue

    async def _simulate_client(self, client: str):
        """
        Simulates a single client's trading activity.

        Each client:
        - Waits a random interval between trades
        - Picks a random instrument
        - Picks a random direction (BUY or SELL)
        - Picks a random trade size
        - Executes the trade at the current bid or ask price

        Args:
            client: The client name e.g. "ViltrumFinance"
        """
        print(f"[Simulator] Starting client: {client}")

        while not self.stop_event.is_set():
            interval = random.uniform(TRADE_INTERVAL_MIN, TRADE_INTERVAL_MAX)

            # Sleep in small chunks so we can respond to stop_event quickly
            elapsed = 0.0
            while elapsed < interval and not self.stop_event.is_set():
                await asyncio.sleep(0.1)
                elapsed += 0.1

            if self.stop_event.is_set():
                break

            if not self.current_prices:
                continue

            instrument = random.choice(list(INSTRUMENTS.keys()))
            direction = random.choice([Direction.BUY, Direction.SELL])

            size_steps = random.randint(
                MIN_TRADE_SIZE // TRADE_SIZE_STEP,
                MAX_TRADE_SIZE // TRADE_SIZE_STEP
            )
            size = size_steps * TRADE_SIZE_STEP

            price_data = self.current_prices.get(instrument)
            if not price_data:
                continue

            if direction == Direction.BUY:
                trade_price = price_data.ask
            else:
                trade_price = price_data.bid

            trade = Trade(
                client=client,
                instrument=instrument,
                direction=direction,
                size=float(size),
                price=trade_price,
            )

            self.book.process_trade(trade)

            print(
                f"[Simulator] {client} {direction.value} "
                f"{size:,.0f} {instrument} @ {trade_price:.5f}"
            )

    async def run(self):
        """
        Starts the price listener and all client simulators
        as concurrent async tasks.

        All clients trade simultaneously and independently.
        """
        print(f"[Simulator] Starting {len(CLIENTS)} clients")

        tasks = [asyncio.create_task(self._price_listener())]

        for client in CLIENTS:
            task = asyncio.create_task(self._simulate_client(client))
            tasks.append(task)

        await asyncio.gather(*tasks)