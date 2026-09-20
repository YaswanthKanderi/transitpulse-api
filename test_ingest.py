import csv
import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from transit.ingest import RowError, ingest_rows, validate_row
from transit.models import StopEvent

GOOD = {
    "trip_ref": "96-0001",
    "route": "96",
    "direction": "0",
    "stop_code": "S1",
    "sequence": "1",
    "scheduled_arrival": "2026-03-02T08:00:00+11:00",
    "actual_arrival": "2026-03-02T08:02:00+11:00",
}


def row(**overrides):
    return {**GOOD, **overrides}


def test_validate_row_accepts_good_row():
    cleaned = validate_row(GOOD)
    assert cleaned["sequence"] == 1
    assert cleaned["direction"] == 0


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"route": ""}, "missing values"),
        ({"direction": "2"}, "direction must be 0 or 1"),
        ({"sequence": "abc"}, "whole numbers"),
        ({"sequence": "0"}, "sequence must be 1 or more"),
        ({"scheduled_arrival": "yesterday"}, "not an ISO timestamp"),
        ({"actual_arrival": "2026-03-02T20:00:00+11:00"}, "more than 6 hours"),
    ],
)
def test_validate_row_rejects_bad_rows(overrides, message):
    with pytest.raises(RowError, match=message):
        validate_row(row(**overrides))


@pytest.mark.django_db
def test_ingest_reports_rejected_rows_and_keeps_good_ones():
    rows = [GOOD, row(trip_ref="96-0002", direction="9"), row(sequence="2")]
    result = ingest_rows(rows)
    assert result.created == 2
    assert len(result.rejected) == 1
    assert result.rejected[0][0] == 3  # second data row is file line 3
    assert StopEvent.objects.count() == 2


@pytest.mark.django_db
def test_ingest_is_idempotent():
    ingest_rows([GOOD])
    again = ingest_rows([GOOD])
    assert again.created == 0
    assert again.skipped_duplicates == 1
    assert StopEvent.objects.count() == 1


@pytest.mark.django_db
def test_ingest_csv_command_end_to_end(tmp_path):
    path = tmp_path / "events.csv"
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(GOOD))
    writer.writeheader()
    writer.writerow(GOOD)
    path.write_text(buffer.getvalue())

    out = io.StringIO()
    call_command("ingest_csv", str(path), stdout=out)
    assert "Created 1" in out.getvalue()


@pytest.mark.django_db
def test_ingest_csv_command_rejects_missing_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("trip_ref,route\nA,96\n")
    with pytest.raises(CommandError, match="missing columns"):
        call_command("ingest_csv", str(path))
