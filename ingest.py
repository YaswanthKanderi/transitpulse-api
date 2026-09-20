"""Validated CSV ingestion.

Real feeds are messy, so every row is checked before it is written and bad
rows are reported back instead of crashing the whole load.

Expected columns:
    trip_ref, route, direction, stop_code, sequence,
    scheduled_arrival, actual_arrival   (ISO 8601 timestamps)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from .models import Route, Stop, StopEvent, Trip

REQUIRED_COLUMNS = {
    "trip_ref",
    "route",
    "direction",
    "stop_code",
    "sequence",
    "scheduled_arrival",
    "actual_arrival",
}
# A delay of more than six hours in either direction is almost certainly a
# data fault (wrong date, wrong timezone), not a real service disruption.
MAX_ABS_DELAY_S = 6 * 3600


class RowError(ValueError):
    """Raised for a row that fails validation."""


@dataclass
class IngestResult:
    created: int = 0
    skipped_duplicates: int = 0
    rejected: list[tuple[int, str]] = field(default_factory=list)


def _parse_time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip())
    except (ValueError, AttributeError) as exc:
        raise RowError(f"{label} is not an ISO timestamp: {value!r}") from exc
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def validate_row(row: dict) -> dict:
    """Return a cleaned copy of the row or raise RowError."""
    missing = [c for c in REQUIRED_COLUMNS if not (row.get(c) or "").strip()]
    if missing:
        raise RowError(f"missing values for: {', '.join(sorted(missing))}")
    try:
        direction = int(row["direction"])
        sequence = int(row["sequence"])
    except ValueError as exc:
        raise RowError("direction and sequence must be whole numbers") from exc
    if direction not in (0, 1):
        raise RowError(f"direction must be 0 or 1, got {direction}")
    if sequence < 1:
        raise RowError(f"sequence must be 1 or more, got {sequence}")
    scheduled = _parse_time(row["scheduled_arrival"], "scheduled_arrival")
    actual = _parse_time(row["actual_arrival"], "actual_arrival")
    if abs((actual - scheduled).total_seconds()) > MAX_ABS_DELAY_S:
        raise RowError("delay is more than 6 hours, likely a timestamp fault")
    return {
        "trip_ref": row["trip_ref"].strip(),
        "route": row["route"].strip(),
        "direction": direction,
        "stop_code": row["stop_code"].strip(),
        "sequence": sequence,
        "scheduled_arrival": scheduled,
        "actual_arrival": actual,
    }


@transaction.atomic
def ingest_rows(rows: Iterable[dict]) -> IngestResult:
    """Validate and store rows. Re-running the same file is safe."""
    result = IngestResult()
    routes: dict[str, Route] = {}
    stops: dict[str, Stop] = {}
    trips: dict[str, Trip] = {}

    for line_no, raw in enumerate(rows, start=2):  # line 1 is the header
        try:
            row = validate_row(raw)
        except RowError as exc:
            result.rejected.append((line_no, str(exc)))
            continue

        route = routes.get(row["route"])
        if route is None:
            route, _ = Route.objects.get_or_create(short_name=row["route"])
            routes[row["route"]] = route

        stop = stops.get(row["stop_code"])
        if stop is None:
            stop, _ = Stop.objects.get_or_create(
                code=row["stop_code"], defaults={"name": row["stop_code"]}
            )
            stops[row["stop_code"]] = stop

        trip = trips.get(row["trip_ref"])
        if trip is None:
            trip, _ = Trip.objects.get_or_create(
                trip_ref=row["trip_ref"],
                defaults={"route": route, "direction": row["direction"]},
            )
            trips[row["trip_ref"]] = trip

        _, created = StopEvent.objects.get_or_create(
            trip=trip,
            sequence=row["sequence"],
            defaults={
                "stop": stop,
                "scheduled_arrival": row["scheduled_arrival"],
                "actual_arrival": row["actual_arrival"],
            },
        )
        if created:
            result.created += 1
        else:
            result.skipped_duplicates += 1
    return result
