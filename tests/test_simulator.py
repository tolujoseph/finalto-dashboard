"""
Unit tests for backend/simulator.py — mock client trading simulator.

The simulator is dominated by random sleeps (5-15s per trade), so these
tests target the deterministic pieces directly rather than running the
full client loop in real time: the price listener task, and a single
iteration of trade construction with randomness patched out.
"""

import asyncio

import pytest

from backend.book import Book
from backend.models import Direction, Price
from backend.simulator import TradingSimulator
from config import INSTRUMENTS


def make_price(instrument, mid=1.1000, spread=0.0001):
    return Price(
        instrument=instrument,
        bid=mid - spread / 2,
        ask=mid + spread / 2,
        mid=mid,
        spread=spread,
    )


@pytest.fixture
def book():
    return Book()


@pytest.fixture
def simulator(book):
    return TradingSimulator(book, asyncio.Queue())


@pytest.mark.asyncio
class TestPriceListener:
    async def test_updates_current_prices_and_book_from_queue(self, simulator, book):
        prices = {"EURUSD": make_price("EURUSD")}
        await simulator.price_queue.put(prices)

        listener_task = asyncio.create_task(simulator._price_listener())
        await asyncio.sleep(0.05)
        simulator.stop_event.set()
        await asyncio.wait_for(listener_task, timeout=2.0)

        assert simulator.current_prices == prices
        assert book.history  # update_prices was called, appending a snapshot

    async def test_stops_when_stop_event_is_set(self, simulator):
        simulator.stop_event.set()
        # Should return promptly without consuming any prices
        await asyncio.wait_for(simulator._price_listener(), timeout=2.0)
        assert simulator.current_prices == {}


@pytest.mark.asyncio
class TestSimulateClientTradeConstruction:
    async def test_buy_direction_trades_at_ask_price(self, simulator, monkeypatch):
        instrument = "EURUSD"
        price = make_price(instrument, mid=1.1000, spread=0.0002)
        simulator.current_prices = {instrument: price}

        monkeypatch.setattr("random.uniform", lambda a, b: 0.0)
        monkeypatch.setattr("random.choice", lambda seq: (
            instrument if seq == list(INSTRUMENTS.keys()) else Direction.BUY
        ))
        monkeypatch.setattr("random.randint", lambda a, b: a)

        recorded = {}
        original_process_trade = simulator.book.process_trade

        def capture(trade):
            recorded["trade"] = trade
            simulator.stop_event.set()
            original_process_trade(trade)

        monkeypatch.setattr(simulator.book, "process_trade", capture)

        await asyncio.wait_for(simulator._simulate_client("ClientA"), timeout=2.0)

        assert recorded["trade"].direction == Direction.BUY
        assert recorded["trade"].price == price.ask

    async def test_sell_direction_trades_at_bid_price(self, simulator, monkeypatch):
        instrument = "EURUSD"
        price = make_price(instrument, mid=1.1000, spread=0.0002)
        simulator.current_prices = {instrument: price}

        monkeypatch.setattr("random.uniform", lambda a, b: 0.0)
        monkeypatch.setattr("random.choice", lambda seq: (
            instrument if seq == list(INSTRUMENTS.keys()) else Direction.SELL
        ))
        monkeypatch.setattr("random.randint", lambda a, b: a)

        recorded = {}
        original_process_trade = simulator.book.process_trade

        def capture(trade):
            recorded["trade"] = trade
            simulator.stop_event.set()
            original_process_trade(trade)

        monkeypatch.setattr(simulator.book, "process_trade", capture)

        await asyncio.wait_for(simulator._simulate_client("ClientA"), timeout=2.0)

        assert recorded["trade"].direction == Direction.SELL
        assert recorded["trade"].price == price.bid

    async def test_skips_trading_when_no_prices_available_yet(self, simulator, monkeypatch):
        # current_prices stays empty; the client loop should not crash,
        # it just keeps looping until stop_event is set.
        # NOTE: interval must stay > 0 here. The simulator's inner sleep
        # loop is the only await point in each outer iteration — an
        # interval of 0.0 means that loop body never runs, so the client
        # busy-loops forever and starves every other task (including the
        # one that sets stop_event below), hanging the test permanently.
        monkeypatch.setattr("random.uniform", lambda a, b: 0.15)

        async def stop_after_delay():
            await asyncio.sleep(0.3)
            simulator.stop_event.set()

        asyncio.create_task(stop_after_delay())
        await asyncio.wait_for(simulator._simulate_client("ClientA"), timeout=2.0)
        # No exception raised means the "continue on missing prices" path held
