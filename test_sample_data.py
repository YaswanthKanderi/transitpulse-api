import pytest
from django.core.management import call_command

from transit.models import Route, StopEvent


@pytest.mark.django_db
def test_generate_sample_data_is_reproducible():
    call_command("generate_sample_data", days=1, seed=7, clear=True, verbosity=0)
    first = list(
        StopEvent.objects.order_by("trip__trip_ref", "sequence").values_list(
            "actual_arrival", flat=True
        )[:50]
    )
    call_command("generate_sample_data", days=1, seed=7, clear=True, verbosity=0)
    second = list(
        StopEvent.objects.order_by("trip__trip_ref", "sequence").values_list(
            "actual_arrival", flat=True
        )[:50]
    )
    assert Route.objects.count() == 3
    assert first == second
