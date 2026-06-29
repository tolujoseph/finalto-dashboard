"""
Unit tests for backend/book.py — the core PnL and position engine.

Covers:
- Initial book state
- process_trade: direction flipping, averaging, realised PnL, spread revenue
- update_prices: unrealised PnL calculation, history bookkeeping
- get_current_state
"""

import pytest

from backend.book import Book
from backend.models import Direction, Price, Trade
from config import INSTRUMENTS

INSTRUMENT = "EURUSD"


def make_trade(client="ClientA", instrument=INSTRUMENT, direction=Direction.BUY,
                size=10_000.0, price=1.0850):
    return Trade(
        client=client,
        instrument=instrument,
        direction=direction,
        size=size,
        price=price,
    )


def make_price(instrument=INSTRUMENT, mid=1.0850, spread=0.0001):
    return Price(
        instrument=instrument,
        bid=mid - spread / 2,
        ask=mid + spread / 2,
        mid=mid,
        spread=spread,
    )


class TestInitialisation:
    def test_creates_flat_position_for_every_configured_instrument(self):
        book = Book()
        assert set(book.positions.keys()) == set(INSTRUMENTS.keys())
        for position in book.positions.values():
            assert position.net_size == 0.0
            assert position.avg_entry_price == 0.0
            assert position.unrealised_pnl == 0.0
            assert position.realised_pnl == 0.0

    def test_starts_with_empty_running_totals(self):
        book = Book()
        assert book.client_yield == {}
        assert book.total_spread_revenue == 0.0
        assert book.total_realised_pnl == 0.0
        assert book.current_prices == {}
        assert book.history == []

    def test_get_current_state_with_no_history_returns_default_book_state(self):
        book = Book()
        state = book.get_current_state()
        assert state.positions == {}
        assert state.total_pnl == 0.0


class TestProcessTradeDirection:
    def test_client_buy_makes_finalto_short(self):
        book = Book()
        book.process_trade(make_trade(direction=Direction.BUY, size=10_000))
        assert book.positions[INSTRUMENT].net_size == -10_000

    def test_client_sell_makes_finalto_long(self):
        book = Book()
        book.process_trade(make_trade(direction=Direction.SELL, size=10_000))
        assert book.positions[INSTRUMENT].net_size == 10_000

    def test_unknown_instrument_raises_key_error(self):
        book = Book()
        trade = make_trade(instrument="NOTREAL")
        with pytest.raises(KeyError):
            book.process_trade(trade)


class TestAverageEntryPrice:
    def test_fresh_position_entry_price_is_trade_price(self):
        book = Book()
        book.process_trade(make_trade(direction=Direction.SELL, size=10_000, price=1.1000))
        assert book.positions[INSTRUMENT].avg_entry_price == pytest.approx(1.1000)

    def test_adding_same_direction_uses_weighted_average(self):
        book = Book()
        # Client sells 10k @ 1.1000 -> Finalto long 10k @ 1.1000
        book.process_trade(make_trade(direction=Direction.SELL, size=10_000, price=1.1000))
        # Client sells another 10k @ 1.2000 -> Finalto long 20k, weighted avg
        book.process_trade(make_trade(direction=Direction.SELL, size=10_000, price=1.2000))

        position = book.positions[INSTRUMENT]
        assert position.net_size == 20_000
        expected_avg = (10_000 * 1.1000 + 10_000 * 1.2000) / 20_000
        assert position.avg_entry_price == pytest.approx(expected_avg)

    def test_flip_resets_entry_price_to_trade_price(self):
        book = Book()
        # Finalto long 10k @ 1.1000
        book.process_trade(make_trade(direction=Direction.SELL, size=10_000, price=1.1000))
        # Client buys 30k -> Finalto sells 30k, flips from +10k to -20k
        book.process_trade(make_trade(direction=Direction.BUY, size=30_000, price=1.1500))

        position = book.positions[INSTRUMENT]
        assert position.net_size == -20_000
        assert position.avg_entry_price == pytest.approx(1.1500)

    def test_partial_reduction_leaves_entry_price_unchanged(self):
        book = Book()
        # Finalto long 10k @ 1.1000
        book.process_trade(make_trade(direction=Direction.SELL, size=10_000, price=1.1000))
        # Client buys 4k -> Finalto reduces to +6k, partial close (not flip)
        book.process_trade(make_trade(direction=Direction.BUY, size=4_000, price=1.3000))

        position = book.positions[INSTRUMENT]
        assert position.net_size == 6_000
        assert position.avg_entry_price == pytest.approx(1.1000)


class TestRealisedPnl:
    def test_no_realised_pnl_on_fresh_position(self):
        book = Book()
        book.process_trade(make_trade(direction=Direction.SELL, size=10_000, price=1.1000))
        assert book.positions[INSTRUMENT].realised_pnl == 0.0
        assert book.total_realised_pnl == 0.0

    def test_no_realised_pnl_when_adding_to_position(self):
        book = Book()
        book.process_trade(make_trade(direction=Direction.SELL, size=10_000, price=1.1000))
        book.process_trade(make_trade(direction=Direction.SELL, size=10_000, price=1.2000))
        assert book.positions[INSTRUMENT].realised_pnl == 0.0

    def test_partial_close_of_long_position_realises_profit(self):
        book = Book()
        # Finalto long 10k @ 1.1000
        book.process_trade(make_trade(direction=Direction.SELL, size=10_000, price=1.1000))
        # Client buys 4k @ 1.2000 -> Finalto closes 4k long at a higher price -> profit
        book.process_trade(make_trade(direction=Direction.BUY, size=4_000, price=1.2000))

        position = book.positions[INSTRUMENT]
        expected = 4_000 * (1.2000 - 1.1000) * 0.01
        assert position.realised_pnl == pytest.approx(expected)
        assert book.total_realised_pnl == pytest.approx(expected)

    def test_partial_close_of_long_position_realises_loss(self):
        book = Book()
        book.process_trade(make_trade(direction=Direction.SELL, size=10_000, price=1.2000))
        # Price dropped before client buys back -> Finalto realises a loss
        book.process_trade(make_trade(direction=Direction.BUY, size=4_000, price=1.1000))

        position = book.positions[INSTRUMENT]
        expected = 4_000 * (1.1000 - 1.2000) * 0.01
        assert position.realised_pnl == pytest.approx(expected)
        assert expected < 0

    def test_partial_close_of_short_position_realises_profit(self):
        book = Book()
        # Finalto short 10k @ 1.1000 (client bought)
        book.process_trade(make_trade(direction=Direction.BUY, size=10_000, price=1.1000))
        # Client sells 4k @ 1.0000 -> Finalto buys back lower -> profit
        book.process_trade(make_trade(direction=Direction.SELL, size=4_000, price=1.0000))

        position = book.positions[INSTRUMENT]
        expected = 4_000 * (1.1000 - 1.0000) * 0.01
        assert position.realised_pnl == pytest.approx(expected)

    def test_exact_close_zeroes_net_size_and_realises_full_pnl(self):
        book = Book()
        book.process_trade(make_trade(direction=Direction.SELL, size=10_000, price=1.1000))
        book.process_trade(make_trade(direction=Direction.BUY, size=10_000, price=1.2000))

        position = book.positions[INSTRUMENT]
        assert position.net_size == 0.0
        expected = 10_000 * (1.2000 - 1.1000) * 0.01
        assert position.realised_pnl == pytest.approx(expected)

    def test_flip_only_realises_pnl_on_the_closed_portion(self):
        book = Book()
        # Finalto long 10k @ 1.1000
        book.process_trade(make_trade(direction=Direction.SELL, size=10_000, price=1.1000))
        # Client buys 30k @ 1.1500 -> closes 10k long (realised) and opens 20k short
        book.process_trade(make_trade(direction=Direction.BUY, size=30_000, price=1.1500))

        position = book.positions[INSTRUMENT]
        expected_realised = 10_000 * (1.1500 - 1.1000) * 0.01
        assert position.realised_pnl == pytest.approx(expected_realised)
        assert position.net_size == -20_000

    def test_realised_pnl_accumulates_across_multiple_closes(self):
        book = Book()
        book.process_trade(make_trade(direction=Direction.SELL, size=10_000, price=1.1000))
        book.process_trade(make_trade(direction=Direction.BUY, size=4_000, price=1.2000))
        book.process_trade(make_trade(direction=Direction.BUY, size=4_000, price=1.3000))

        position = book.positions[INSTRUMENT]
        expected = (
            4_000 * (1.2000 - 1.1000) * 0.01 +
            4_000 * (1.3000 - 1.1000) * 0.01
        )
        assert position.realised_pnl == pytest.approx(expected)
        assert book.total_realised_pnl == pytest.approx(expected)


class TestSpreadRevenue:
    def test_zero_spread_revenue_when_price_unknown(self):
        book = Book()
        book.process_trade(make_trade(size=10_000))
        assert book.total_spread_revenue == 0.0
        assert book.client_yield["ClientA"] == 0.0

    def test_spread_revenue_uses_current_spread_for_instrument(self):
        book = Book()
        book.current_prices = {INSTRUMENT: make_price(spread=0.0002)}
        book.process_trade(make_trade(size=10_000))

        expected = 0.0002 * 10_000
        assert book.total_spread_revenue == pytest.approx(expected)
        assert book.client_yield["ClientA"] == pytest.approx(expected)

    def test_client_yield_tracked_separately_per_client(self):
        book = Book()
        book.current_prices = {INSTRUMENT: make_price(spread=0.0001)}
        book.process_trade(make_trade(client="ClientA", size=10_000))
        book.process_trade(make_trade(client="ClientB", size=20_000))

        assert book.client_yield["ClientA"] == pytest.approx(0.0001 * 10_000)
        assert book.client_yield["ClientB"] == pytest.approx(0.0001 * 20_000)
        assert book.total_spread_revenue == pytest.approx(
            0.0001 * 10_000 + 0.0001 * 20_000
        )

    def test_client_yield_accumulates_across_trades(self):
        book = Book()
        book.current_prices = {INSTRUMENT: make_price(spread=0.0001)}
        book.process_trade(make_trade(client="ClientA", size=10_000))
        book.process_trade(make_trade(client="ClientA", size=5_000))

        assert book.client_yield["ClientA"] == pytest.approx(0.0001 * 15_000)


class TestUpdatePrices:
    def test_flat_position_has_zero_unrealised_pnl(self):
        book = Book()
        book.update_prices({INSTRUMENT: make_price(mid=1.2000)})
        assert book.positions[INSTRUMENT].unrealised_pnl == 0.0

    def test_long_position_gains_when_price_rises(self):
        book = Book()
        book.process_trade(make_trade(direction=Direction.SELL, size=10_000, price=1.1000))
        book.update_prices({INSTRUMENT: make_price(mid=1.2000)})

        expected = 10_000 * (1.2000 - 1.1000) * 0.01
        assert book.positions[INSTRUMENT].unrealised_pnl == pytest.approx(expected)
        assert expected > 0

    def test_long_position_loses_when_price_falls(self):
        book = Book()
        book.process_trade(make_trade(direction=Direction.SELL, size=10_000, price=1.2000))
        book.update_prices({INSTRUMENT: make_price(mid=1.1000)})

        expected = 10_000 * (1.1000 - 1.2000) * 0.01
        assert book.positions[INSTRUMENT].unrealised_pnl == pytest.approx(expected)
        assert expected < 0

    def test_short_position_gains_when_price_falls(self):
        book = Book()
        book.process_trade(make_trade(direction=Direction.BUY, size=10_000, price=1.2000))
        book.update_prices({INSTRUMENT: make_price(mid=1.1000)})

        expected = -10_000 * (1.1000 - 1.2000) * 0.01
        assert book.positions[INSTRUMENT].unrealised_pnl == pytest.approx(expected)
        assert expected > 0

    def test_missing_price_for_open_position_zeroes_unrealised_pnl(self):
        book = Book()
        book.process_trade(make_trade(direction=Direction.SELL, size=10_000, price=1.1000))
        book.update_prices({})
        assert book.positions[INSTRUMENT].unrealised_pnl == 0.0

    def test_total_unrealised_pnl_sums_across_instruments(self):
        book = Book()
        book.process_trade(make_trade(instrument="EURUSD", direction=Direction.SELL,
                                       size=10_000, price=1.1000))
        book.process_trade(make_trade(instrument="GBPUSD", direction=Direction.SELL,
                                       size=10_000, price=1.2000))

        book.update_prices({
            "EURUSD": make_price(instrument="EURUSD", mid=1.2000),
            "GBPUSD": make_price(instrument="GBPUSD", mid=1.3000),
        })

        state = book.get_current_state()
        expected = (
            10_000 * (1.2000 - 1.1000) * 0.01 +
            10_000 * (1.3000 - 1.2000) * 0.01
        )
        assert state.total_unrealised_pnl == pytest.approx(expected)

    def test_appends_snapshot_to_history(self):
        book = Book()
        book.update_prices({INSTRUMENT: make_price()})
        assert len(book.history) == 1

    def test_history_grows_with_each_update(self):
        book = Book()
        for _ in range(5):
            book.update_prices({INSTRUMENT: make_price()})
        assert len(book.history) == 5

    def test_history_bounded_at_max_history_points(self, monkeypatch):
        monkeypatch.setattr("backend.book.MAX_HISTORY_POINTS", 3)
        book = Book()
        for _ in range(5):
            book.update_prices({INSTRUMENT: make_price()})
        assert len(book.history) == 3

    def test_history_drops_oldest_snapshot_when_bounded(self, monkeypatch):
        monkeypatch.setattr("backend.book.MAX_HISTORY_POINTS", 2)
        book = Book()
        book.update_prices({INSTRUMENT: make_price(mid=1.0)})
        book.update_prices({INSTRUMENT: make_price(mid=2.0)})
        book.update_prices({INSTRUMENT: make_price(mid=3.0)})

        # Oldest snapshot (mid=1.0) should have been evicted
        assert len(book.history) == 2
        timestamps_seen_mids = [s.timestamp for s in book.history]
        assert len(timestamps_seen_mids) == 2


class TestGetCurrentState:
    def test_returns_most_recent_snapshot(self):
        book = Book()
        book.update_prices({INSTRUMENT: make_price(mid=1.1000)})
        first_state = book.get_current_state()
        book.update_prices({INSTRUMENT: make_price(mid=1.5000)})
        second_state = book.get_current_state()

        assert second_state is book.history[-1]
        assert first_state is not second_state

    def test_state_is_independent_snapshot_not_live_reference(self):
        book = Book()
        book.process_trade(make_trade(direction=Direction.SELL, size=10_000, price=1.1000))
        book.update_prices({INSTRUMENT: make_price(mid=1.1000)})
        snapshot = book.get_current_state()

        # Mutating the live position afterwards must not change the snapshot
        book.positions[INSTRUMENT].net_size = 999_999
        assert snapshot.positions[INSTRUMENT].net_size == 10_000
