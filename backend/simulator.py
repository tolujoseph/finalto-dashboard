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

    def __init__(self, book: Book, price_queue: asyncio.Queue):
        """
        Args:
            book: The Book instance to send trades to.
            price_queue: Queue to read current prices from.
        """
        self.book = book
        self.price_queue = price_queue

        # Shared current prices updated from the streamer
        self.current_prices = {}

    async def _price_listener(self):
        """
        Listens to the price queue and updates current prices.

        Runs as a background task so all client simulators
        always have access to the latest prices.
        """
        while True:
            prices = await self.price_queue.get()
            self.current_prices = prices

            # Update the book with new prices for PnL recalculation
            self.book.update_prices(prices)

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
            client: The client name e.g. "AlphaCapital"
        """
        print(f"[Simulator] Starting client: {client}")

        while True:
            # Wait random interval before next trade
            interval = random.uniform(TRADE_INTERVAL_MIN, TRADE_INTERVAL_MAX)
            await asyncio.sleep(interval)

            # Skip if we don't have prices yet
            if not self.current_prices:
                continue

            # Pick random instrument and direction
            instrument = random.choice(list(INSTRUMENTS.keys()))
            direction = random.choice([Direction.BUY, Direction.SELL])

            # Pick random trade size as a multiple of TRADE_SIZE_STEP
            size_steps = random.randint(
                MIN_TRADE_SIZE // TRADE_SIZE_STEP,
                MAX_TRADE_SIZE // TRADE_SIZE_STEP
            )
            size = size_steps * TRADE_SIZE_STEP

            # Get current price for chosen instrument
            price_data = self.current_prices.get(instrument)
            if not price_data:
                continue

            # Client buys at ask price, sells at bid price
            if direction == Direction.BUY:
                trade_price = price_data.ask
            else:
                trade_price = price_data.bid

            # Create and validate the trade using Pydantic
            trade = Trade(
                client=client,
                instrument=instrument,
                direction=direction,
                size=float(size),
                price=trade_price,
            )

            # Send trade to the book
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

        # Start price listener
        tasks = [asyncio.create_task(self._price_listener())]

        # Start one trading task per client
        for client in CLIENTS:
            task = asyncio.create_task(self._simulate_client(client))
            tasks.append(task)

        # Run all tasks concurrently
        await asyncio.gather(*tasks)