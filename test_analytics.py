import pandas as pd
import pytest

from transit import analytics


def frame(delays, start="2026-03-02 08:00", step_min=10, stop="S1", direction=0):
    """Build a DataFrame the way events_to_frame would, from a list of delays."""
    scheduled = pd.date_range(
        start, periods=len(delays), freq=f"{step_min}min", tz="Australia/Melbourne"
    )
    actual = scheduled + pd.to_timedelta(delays, unit="s")
    return pd.DataFrame(
        {
            "trip_ref": [f"T{i}" for i in range(len(delays))],
            "route": "96",
            "direction": direction,
            "stop_code": stop,
            "stop_name": stop,
            "sequence": 1,
            "scheduled_arrival": scheduled,
            "actual_arrival": actual,
            "delay_s": [float(d) for d in delays],
        }
    )


def test_on_time_performance_classifies_early_on_time_and_late():
    # early by 2 min, on time, on time (exactly 5 min late), late by 6 min
    df = frame([-120, 0, 300, 360])
    result = analytics.on_time_performance(df, early_s=60, late_s=300)
    assert result["events"] == 4
    assert result["early_pct"] == 25.0
    assert result["late_pct"] == 25.0
    assert result["on_time_pct"] == 50.0
    assert result["mean_delay_s"] == 135.0


def test_on_time_performance_handles_empty_input():
    empty = frame([]).iloc[0:0]
    result = analytics.on_time_performance(empty)
    assert result["events"] == 0
    assert result["on_time_pct"] is None


def test_delay_by_hour_groups_on_scheduled_hour():
    # 08:00, 08:10, ... 08:50 then 09:00 with different delays
    df = frame([60] * 6 + [600])
    hours = {h["hour"]: h for h in analytics.delay_by_hour(df)}
    assert hours[8]["events"] == 6
    assert hours[8]["mean_delay_s"] == 60.0
    assert hours[8]["on_time_pct"] == 100.0
    assert hours[9]["on_time_pct"] == 0.0


def test_worst_stops_ignores_stops_with_too_few_events():
    busy = frame([200] * 6, stop="BUSY")
    quiet = frame([900], stop="QUIET")
    df = pd.concat([busy, quiet], ignore_index=True)
    stops = analytics.worst_stops(df, n=5, min_events=5)
    assert [s["stop_code"] for s in stops] == ["BUSY"]


def test_headway_detects_bunching():
    # Trip 2 is 500 s late, so trip 3 (on time) arrives only 100 s behind it.
    df = frame([0, 0, 500, 0, 0])
    summary = analytics.headway_summary(df)
    assert summary["headways_measured"] == 4
    # headway errors are 0, 500, 500, 0 seconds
    assert summary["mean_headway_error_s"] == 250.0
    # only the 100 s gap is under 25% of the 600 s schedule
    assert summary["bunching_pct"] == 25.0


def test_headway_ignores_long_gaps_between_services():
    df = frame([0, 0], step_min=120)
    assert analytics.headway_summary(df)["headways_measured"] == 0


@pytest.mark.django_db
def test_events_to_frame_computes_delay(route, stop, make_event):
    from transit.models import StopEvent

    make_event(route, stop, delay_s=90)
    df = analytics.events_to_frame(StopEvent.objects.all())
    assert list(df["delay_s"]) == [90.0]
    assert df["route"].iloc[0] == "96"
