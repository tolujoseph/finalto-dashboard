"""
Unit tests for backend/models.py — Pydantic data models.

Covers field validation, defaults, enum behaviour, and computed properties.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.models import BookState, Direction, Position, Price, Trade


class TestDirection:
    def test_has_buy_and_sell_members(self):
        assert Direction.BUY == "BUY"
        assert Direction.SELL == "SELL"

    def test_is_a_string_enum(self):
        assert isinstance(Direction.BUY, str)

    def test_accepts_raw_string_value(self):
        assert Direction("BUY") is Direction.BUY

    def test_rejects_invalid_value(self):
        with pytest.raises(ValueError):
            Direction("HOLD")


class TestPrice:
    def test_constructs_with_required_fields(self):
        price = Price(instrument="EURUSD", bid=1.0849, ask=1.0851, mid=1.0850, spread=0.0002)
        assert price.instrument == "EURUSD"
        assert price.bid == 1.0849
        assert price.ask == 1.0851
        assert price.mid == 1.0850
        assert price.spread == 0.0002

    def test_defaults_timestamp_to_now_utc(self):
        before = datetime.now(timezone.utc)
        price = Price(instrument="EURUSD", bid=1.0, ask=1.0, mid=1.0, spread=0.0)
        after = datetime.now(timezone.utc)
        assert before <= price.timestamp <= after

    def test_accepts_explicit_timestamp(self):
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        price = Price(instrument="EURUSD", bid=1.0, ask=1.0, mid=1.0, spread=0.0, timestamp=ts)
        assert price.timestamp == ts

    def test_missing_required_field_raises_validation_error(self):
        with pytest.raises(ValidationError):
            Price(instrument="EURUSD", bid=1.0, ask=1.0, mid=1.0)

    def test_non_numeric_bid_raises_validation_error(self):
        with pytest.raises(ValidationError):
            Price(instrument="EURUSD", bid="not-a-number", ask=1.0, mid=1.0, spread=0.0)

    def test_coerces_numeric_string_to_float(self):
        price = Price(instrument="EURUSD", bid="1.0849", ask=1.0851, mid=1.0850, spread=0.0002)
        assert price.bid == pytest.approx(1.0849)

    def test_allows_zero_values(self):
        price = Price(instrument="EURUSD", bid=0.0, ask=0.0, mid=0.0, spread=0.0)
        assert price.mid == 0.0

    def test_allows_negative_bid_no_domain_constraint(self):
        # The model itself has no positivity constraint — the streamer
        # enforces non-negative prices, not the Price model.
        price = Price(instrument="EURUSD", bid=-1.0, ask=-0.5, mid=-0.75, spread=0.5)
        assert price.bid == -1.0


class TestTrade:
    def test_constructs_with_required_fields(self):
        trade = Trade(
            client="ClientA",
            instrument="EURUSD",
            direction=Direction.BUY,
            size=10_000.0,
            price=1.0850,
        )
        assert trade.client == "ClientA"
        assert trade.direction == Direction.BUY
        assert trade.size == 10_000.0

    def test_accepts_direction_as_raw_string(self):
        trade = Trade(
            client="ClientA", instrument="EURUSD", direction="SELL",
            size=10_000.0, price=1.0850,
        )
        assert trade.direction == Direction.SELL

    def test_invalid_direction_raises_validation_error(self):
        with pytest.raises(ValidationError):
            Trade(
                client="ClientA", instrument="EURUSD", direction="HOLD",
                size=10_000.0, price=1.0850,
            )

    def test_defaults_timestamp_to_now_utc(self):
        before = datetime.now(timezone.utc)
        trade = Trade(
            client="ClientA", instrument="EURUSD", direction=Direction.BUY,
            size=10_000.0, price=1.0850,
        )
        after = datetime.now(timezone.utc)
        assert before <= trade.timestamp <= after

    def test_zero_size_is_accepted(self):
        trade = Trade(
            client="ClientA", instrument="EURUSD", direction=Direction.BUY,
            size=0.0, price=1.0850,
        )
        assert trade.size == 0.0

    def test_negative_size_is_accepted_no_domain_constraint(self):
        # No model-level constraint forbids this — callers are responsible
        # for only generating non-negative sizes.
        trade = Trade(
            client="ClientA", instrument="EURUSD", direction=Direction.BUY,
            size=-10_000.0, price=1.0850,
        )
        assert trade.size == -10_000.0

    def test_missing_required_field_raises_validation_error(self):
        with pytest.raises(ValidationError):
            Trade(client="ClientA", instrument="EURUSD", direction=Direction.BUY, size=10_000.0)


class TestPosition:
    def test_defaults_to_flat_position(self):
        position = Position(instrument="EURUSD")
        assert position.net_size == 0.0
        assert position.avg_entry_price == 0.0
        assert position.unrealised_pnl == 0.0
        assert position.realised_pnl == 0.0

    def test_total_pnl_sums_realised_and_unrealised(self):
        position = Position(instrument="EURUSD", unrealised_pnl=150.0, realised_pnl=-50.0)
        assert position.total_pnl == 100.0

    def test_total_pnl_zero_when_both_zero(self):
        position = Position(instrument="EURUSD")
        assert position.total_pnl == 0.0

    def test_total_pnl_negative_when_net_loss(self):
        position = Position(instrument="EURUSD", unrealised_pnl=-200.0, realised_pnl=-50.0)
        assert position.total_pnl == -250.0

    def test_net_size_can_be_negative_for_short_position(self):
        position = Position(instrument="EURUSD", net_size=-50_000.0)
        assert position.net_size == -50_000.0


class TestBookState:
    def test_defaults_to_empty_flat_state(self):
        state = BookState()
        assert state.positions == {}
        assert state.client_yield == {}
        assert state.total_pnl == 0.0

    def test_total_pnl_sums_realised_and_unrealised(self):
        state = BookState(total_unrealised_pnl=300.0, total_realised_pnl=-100.0)
        assert state.total_pnl == 200.0

    def test_holds_positions_keyed_by_instrument(self):
        state = BookState(positions={
            "EURUSD": Position(instrument="EURUSD", net_size=10_000.0),
        })
        assert state.positions["EURUSD"].net_size == 10_000.0

    def test_independent_default_dicts_across_instances(self):
        # Mutable defaults ({}) must not be shared between instances.
        state_a = BookState()
        state_a.client_yield["ClientA"] = 100.0
        state_b = BookState()
        assert state_b.client_yield == {}

    def test_defaults_timestamp_to_now_utc(self):
        before = datetime.now(timezone.utc)
        state = BookState()
        after = datetime.now(timezone.utc)
        assert before <= state.timestamp <= after
