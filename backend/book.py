"""
Book management for the Finalto risk management dashboard.

The book tracks Finalto's net positions across all instruments,
calculating PnL in real time as prices move and trades arrive.

Key principle: Finalto always takes the opposite side of client trades.
    Client BUY  -> Finalto SHORT (negative position)
    Client SELL -> Finalto LONG  (positive position)
"""

import asyncio
from backend.models import Trade, Position, BookState, Direction, Price
from config import INSTRUMENTS, MAX_HISTORY_POINTS


class Book:
    """
    Maintains Finalto's real time book of positions and PnL.

    Receives trades from the simulator and price updates from
    the streamer, updating positions and PnL on every event.
    """

    def __init__(self):
        # Initialise a flat position for every instrument
        self.positions: dict[str, Position] = {
            instrument: Position(instrument=instrument)
            for instrument in INSTRUMENTS
        }

        # Spread revenue earned per client
        self.client_yield: dict[str, float] = {}

        # Running totals
        self.total_spread_revenue: float = 0.0
        self.total_realised_pnl: float = 0.0

        # Current prices — updated by the streamer
        self.current_prices: dict[str, Price] = {}

        # Historical book states for the PnL curve chart
        self.history: list[BookState] = []

    def process_trade(self, trade: Trade) -> None:
        """
        Process a client trade and update Finalto's book.

        Finalto takes the opposite side of every client trade.
        Client BUY  -> Finalto SHORT -> negative net_size
        Client SELL -> Finalto LONG  -> positive net_size

        Also calculates spread revenue earned on this trade.

        Args:
            trade: The validated Trade model from the simulator.
        """
        position = self.positions[trade.instrument]
        spread = self.current_prices[trade.instrument].spread \
            if trade.instrument in self.current_prices else 0.0

        # Finalto takes opposite side — flip the direction
        if trade.direction == Direction.BUY:
            finalto_size = -trade.size   # Finalto is short
        else:
            finalto_size = trade.size    # Finalto is long

        previous_size = position.net_size
        new_size = previous_size + finalto_size

        # --- Update average entry price ---
        if previous_size == 0:
            # Fresh position — entry price is simply the trade price
            position.avg_entry_price = trade.price

        elif (previous_size > 0 and finalto_size > 0) or \
             (previous_size < 0 and finalto_size < 0):
            # Adding to existing position in same direction
            # Weighted average of old and new entry prices
            position.avg_entry_price = (
                (abs(previous_size) * position.avg_entry_price +
                 abs(finalto_size) * trade.price) /
                (abs(previous_size) + abs(finalto_size))
            )

        elif abs(finalto_size) >= abs(previous_size):
            # Flipping position — new entry price is the trade price
            position.avg_entry_price = trade.price

        # --- Calculate realised PnL if position is reducing ---
        if previous_size != 0 and (
            (previous_size > 0 and finalto_size < 0) or
            (previous_size < 0 and finalto_size > 0)
        ):
            closed_size = min(abs(previous_size), abs(finalto_size))

            if previous_size > 0:
                realised = closed_size * (
                    trade.price - position.avg_entry_price
                ) * 0.01
            else:
                realised = closed_size * (
                    position.avg_entry_price - trade.price
                ) * 0.01

            position.realised_pnl += realised
            self.total_realised_pnl += realised

        # Update net size
        position.net_size = new_size

        # --- Spread revenue ---
        spread_earned = spread * trade.size
        self.total_spread_revenue += spread_earned

        if trade.client not in self.client_yield:
            self.client_yield[trade.client] = 0.0
        self.client_yield[trade.client] += spread_earned

    def update_prices(self, prices: dict[str, Price]) -> None:
        """
        Update current prices and recalculate unrealised PnL
        for all open positions.

        Called every time the streamer generates new prices.

        Args:
            prices: Dictionary of instrument -> Price model.
        """
        self.current_prices = prices

        total_unrealised = 0.0

        for instrument, position in self.positions.items():
            if instrument not in prices or position.net_size == 0:
                position.unrealised_pnl = 0.0
                continue

            current_mid = prices[instrument].mid

            position.unrealised_pnl = position.net_size * (
                current_mid - position.avg_entry_price
            ) * 0.01

            total_unrealised += position.unrealised_pnl

        # Save a snapshot to history for the PnL curve
        snapshot = self._get_book_state(total_unrealised)
        self.history.append(snapshot)

        # Keep history bounded to prevent memory growing unboundedly
        if len(self.history) > MAX_HISTORY_POINTS:
            self.history.pop(0)

    def _get_book_state(self, total_unrealised: float) -> BookState:
        """
        Generate a BookState snapshot of the current book.

        Args:
            total_unrealised: Pre-calculated total unrealised PnL.

        Returns:
            A validated BookState model representing current book state.
        """
        return BookState(
            positions={k: v.model_copy() for k, v in self.positions.items()},
            client_yield=dict(self.client_yield),
            total_unrealised_pnl=total_unrealised,
            total_realised_pnl=self.total_realised_pnl,
            total_spread_revenue=self.total_spread_revenue,
        )

    def get_current_state(self) -> BookState:
        """
        Get the current book state for broadcasting to the dashboard.

        Returns:
            The most recent BookState snapshot.
        """
        if self.history:
            return self.history[-1]
        return BookState()