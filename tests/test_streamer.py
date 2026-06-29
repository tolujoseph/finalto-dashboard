"""
Unit tests for backend/streamer.py — async market data streamer.

Covers price generation logic deterministically (by patching the random
walk) and the async streaming loop's queue-publishing behaviour.
"""

import asyncio

import pytest

from backend.streamer import MarketDataStreamer
from backend.models import Price
from config import INSTRUMENTS, SPREAD


@pytest.fixture
def queue():
    return asyncio.Queue()


@pytest.fixture
def streamer(queue):
    return MarketDataStreamer(queue)


class TestInitialisation:
    def test_seeds_current_prices_from_config(self, streamer):
        assert streamer.current_prices == INSTRUMENTS

    def test_current_prices_is_independent_copy(self, streamer):
        streamer.current_prices["EURUSD"] = 999.0
        assert INSTRUMENTS["EURUSD"] != 999.0


class TestGeneratePrice:
    def test_returns_price_model_for_requested_instrument(self, streamer):
        price = streamer._generate_price("EURUSD")
        assert isinstance(price, Price)
        assert price.instrument == "EURUSD"

    def test_spread_matches_configured_value(self, streamer):
        price = streamer._generate_price("EURUSD")
        assert price.spread == pytest.approx(SPREAD["EURUSD"], abs=1e-9)

    def test_ask_is_greater_than_bid_by_spread(self, streamer):
        price = streamer._generate_price("GBPUSD")
        assert price.ask - price.bid == pytest.approx(SPREAD["GBPUSD"], abs=1e-4)

    def test_mid_is_midpoint_of_bid_and_ask(self, streamer):
        price = streamer._generate_price("XAUUSD")
        assert price.mid == pytest.approx((price.bid + price.ask) / 2, abs=1e-3)

    def test_updates_internal_current_price_state(self, streamer, monkeypatch):
        monkeypatch.setattr("numpy.random.normal", lambda loc, scale: 0.01)
        before = streamer.current_prices["EURUSD"]
        streamer._generate_price("EURUSD")
        assert streamer.current_prices["EURUSD"] == pytest.approx(before + 0.01)

    def test_price_never_goes_negative_on_large_downward_move(self, streamer, monkeypatch):
        # Force an extreme negative random walk move
        monkeypatch.setattr("numpy.random.normal", lambda loc, scale: -1_000_000)
        price = streamer._generate_price("EURUSD")
        floor = SPREAD["EURUSD"] * 2
        assert price.mid >= floor
        assert streamer.current_prices["EURUSD"] >= floor

    def test_price_floor_is_twice_the_spread(self, streamer, monkeypatch):
        monkeypatch.setattr("numpy.random.normal", lambda loc, scale: -1_000_000)
        price = streamer._generate_price("XAUUSD")
        assert price.mid == pytest.approx(SPREAD["XAUUSD"] * 2)

    def test_zero_move_keeps_mid_unchanged(self, streamer, monkeypatch):
        monkeypatch.setattr("numpy.random.normal", lambda loc, scale: 0.0)
        before = streamer.current_prices["EURUSD"]
        price = streamer._generate_price("EURUSD")
        assert price.mid == pytest.approx(before)

    def test_each_instrument_walks_independently(self, streamer, monkeypatch):
        calls = []

        def fake_normal(loc, scale):
            calls.append(scale)
            return 0.0

        monkeypatch.setattr("numpy.random.normal", fake_normal)
        for instrument in INSTRUMENTS:
            streamer._generate_price(instrument)

        # Each instrument's volatility (scale) should have been used once
        assert len(calls) == len(INSTRUMENTS)


@pytest.mark.asyncio
class TestStreamLoop:
    async def test_publishes_prices_for_all_instruments_to_queue(self, streamer, queue):
        task = asyncio.create_task(streamer.stream())
        try:
            prices = await asyncio.wait_for(queue.get(), timeout=2.0)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        assert set(prices.keys()) == set(INSTRUMENTS.keys())
        for price in prices.values():
            assert isinstance(price, Price)

    async def test_stops_publishing_once_cancelled(self, streamer, queue):
        task = asyncio.create_task(streamer.stream())
        await asyncio.wait_for(queue.get(), timeout=2.0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
