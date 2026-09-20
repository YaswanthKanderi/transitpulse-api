from datetime import UTC, datetime, timedelta

import pytest

from transit.models import Route, Stop, StopEvent, Trip


@pytest.fixture
def make_event():
    """Factory that stores one stop event with a given delay in seconds."""
    counter = {"n": 0}

    def _make(route, stop, delay_s, sequence=1, scheduled=None, direction=0):
        counter["n"] += 1
        scheduled = scheduled or datetime.now(UTC) - timedelta(hours=1)
        trip = Trip.objects.create(
            trip_ref=f"T{counter['n']}", route=route, direction=direction
        )
        return StopEvent.objects.create(
            trip=trip,
            stop=stop,
            sequence=sequence,
            scheduled_arrival=scheduled,
            actual_arrival=scheduled + timedelta(seconds=delay_s),
        )

    return _make


@pytest.fixture
def route(db):
    return Route.objects.create(short_name="96", long_name="Test route")


@pytest.fixture
def stop(db):
    return Stop.objects.create(code="S1", name="First stop")
