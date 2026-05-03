"""
Data models for the Finalto risk management dashboard.

All models use Pydantic for validation, ensuring data integrity
throughout the streaming pipeline.
"""

from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field


class Direction(str, Enum):
    """Trade direction from the client's perspective."""
    BUY = "BUY"
    SELL = "SELL"


class Price(BaseModel):
    """Current bid/ask price for a single instrument."""
    instrument: str
    bid: float
    ask: float
    mid: float
    spread: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Trade(BaseModel):
    """A single trade executed by a client."""
    client: str
    instrument: str
    direction: Direction
    size: float
    price: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Position(BaseModel):
    """Finalto's net position for a single instrument."""
    instrument: str
    net_size: float = 0.0
    avg_entry_price: float = 0.0
    unrealised_pnl: float = 0.0
    realised_pnl: float = 0.0

    @property
    def total_pnl(self) -> float:
        return self.unrealised_pnl + self.realised_pnl


class BookState(BaseModel):
    """Complete state of Finalto's book at a point in time."""
    positions: dict[str, Position] = {}
    client_yield: dict[str, float] = {}
    total_unrealised_pnl: float = 0.0
    total_realised_pnl: float = 0.0
    total_spread_revenue: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total_pnl(self) -> float:
        return self.total_unrealised_pnl + self.total_realised_pnl