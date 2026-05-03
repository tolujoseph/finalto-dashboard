"""
Market data streamer for the Finalto risk management dashboard.

Generates realistic bid/ask prices for each instrument using a random walk,
mimicking a real pricing feed. Prices are published to an asyncio queue
consumed by the simulator and WebSocket server.
"""

import asyncio
import numpy as np
from datetime import datetime, timezone
from backend.models import Price
from config import INSTRUMENTS, SPREAD, VOLATILITY, PRICE_UPDATE_INTERVAL


class MarketDataStreamer:
    """
    Streams bid/ask prices for all configured instruments.

    Uses a random walk to simulate realistic price movements.
    Each tick, the mid price moves up or down by a random amount
    controlled by the instrument's volatility setting.
    """

    def __init__(self, price_queue: asyncio.Queue):
        """
        Args:
            price_queue: asyncio Queue where price updates are published.
                         The simulator and WebSocket server consume from this.
        """
        self.price_queue = price_queue

        # Initialise current mid prices from config starting values
        self.current_prices = {
            instrument: start_price
            for instrument, start_price in INSTRUMENTS.items()
        }

    def _generate_price(self, instrument: str) -> Price:
        """
        Generate a new Price for a single instrument using random walk.

        The mid price moves by a random amount drawn from a normal
        distribution scaled by the instrument's volatility.

        Args:
            instrument: The instrument name e.g. "EURUSD"

        Returns:
            A validated Price model with bid, ask, mid and spread.
        """
        volatility = VOLATILITY[instrument]
        spread = SPREAD[instrument]

        # Random walk - move price up or down by random amount
        # np.random.normal gives us a normally distributed random number
        # mean=0 means equal chance of going up or down
        # volatility controls the size of the move
        move = np.random.normal(loc=0, scale=volatility)
        self.current_prices[instrument] += move

        # Ensure price never goes negative
        self.current_prices[instrument] = max(
            self.current_prices[instrument],
            spread * 2
        )

        mid = self.current_prices[instrument]
        bid = mid - spread / 2
        ask = mid + spread / 2

        return Price(
            instrument=instrument,
            bid=round(bid, 5),
            ask=round(ask, 5),
            mid=round(mid, 5),
            spread=round(spread, 5),
            timestamp=datetime.now(timezone.utc)
        )

    async def stream(self):
        """
        Main streaming loop. Generates prices for all instruments
        every PRICE_UPDATE_INTERVAL seconds and publishes to the queue.

        Runs indefinitely until cancelled.
        """
        print(f"[Streamer] Starting price stream for {list(INSTRUMENTS.keys())}")

        while True:
            # Generate a new price for every instrument
            prices = {}
            for instrument in INSTRUMENTS:
                price = self._generate_price(instrument)
                prices[instrument] = price

            # Publish the full price snapshot to the queue
            await self.price_queue.put(prices)

            # Wait before next update
            await asyncio.sleep(PRICE_UPDATE_INTERVAL)