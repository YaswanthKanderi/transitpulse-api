"""Create reproducible synthetic service data for demos and tests.

The delay model is deliberately simple so the numbers are easy to explain:
a per-route bias, a rush-hour penalty, delay that grows along the route,
random noise, and occasional incidents. An incident holds one trip up for
several minutes from a random stop onward, which makes the next vehicle
arrive close behind it (bunching). It is not real timetable data.
"""

import random
from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from transit.models import Route, Stop, StopEvent, Trip

ROUTES = [
    ("96", "Bourke St to East Brunswick", Route.Mode.TRAM),
    ("901", "Frankston to Melbourne Airport", Route.Mode.BUS),
    ("250", "City to La Trobe University", Route.Mode.BUS),
]
STOPS_PER_ROUTE = 10
STOP_SPACING_S = 240  # scheduled minutes between stops
HEADWAY_S = 600  # a trip every 10 minutes
FIRST_HOUR, LAST_HOUR = 6, 21
RUSH_HOURS = {7, 8, 9, 16, 17, 18}
INCIDENT_PROBABILITY = 0.03
INCIDENT_DELAY_S = (420, 900)


class Command(BaseCommand):
    help = "Generate synthetic stop events for the last N days."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=14)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument(
            "--clear", action="store_true", help="Delete existing data first."
        )

    @transaction.atomic
    def handle(self, *args, days, seed, clear, **options):
        rng = random.Random(seed)
        if clear:
            StopEvent.objects.all().delete()
            Trip.objects.all().delete()
            Route.objects.all().delete()
            Stop.objects.all().delete()

        today = timezone.localdate()
        tz = timezone.get_current_timezone()
        total_events = 0

        for short, long_name, mode in ROUTES:
            route, _ = Route.objects.get_or_create(
                short_name=short, defaults={"long_name": long_name, "mode": mode}
            )
            stops = []
            for s_idx in range(STOPS_PER_ROUTE):
                code = f"{short}-{s_idx + 1:02d}"
                origin = long_name.split(" to ")[0]
                stop, _ = Stop.objects.get_or_create(
                    code=code, defaults={"name": f"{origin} stop {s_idx + 1}"}
                )
                stops.append(stop)

            route_bias_s = rng.uniform(-20, 90)
            events = []
            for day_offset in range(days, 0, -1):
                day = today - timedelta(days=day_offset)
                for hour in range(FIRST_HOUR, LAST_HOUR + 1):
                    for minute_s in range(0, 3600, HEADWAY_S):
                        start = datetime.combine(day, time(hour)) + timedelta(
                            seconds=minute_s
                        )
                        start = timezone.make_aware(start, tz)
                        clock = f"{hour:02d}{minute_s // 60:02d}"
                        trip = Trip.objects.create(
                            trip_ref=f"{short}-{day:%Y%m%d}-{clock}",
                            route=route,
                            direction=0,
                        )
                        rush = 120 if hour in RUSH_HOURS else 0
                        has_incident = rng.random() < INCIDENT_PROBABILITY
                        incident_stop = rng.randint(1, STOPS_PER_ROUTE)
                        incident_s = rng.uniform(*INCIDENT_DELAY_S)
                        for seq, stop in enumerate(stops, start=1):
                            scheduled = start + timedelta(seconds=seq * STOP_SPACING_S)
                            drift = seq * rng.uniform(2, 14)
                            delay = route_bias_s + rush + drift + rng.gauss(0, 45)
                            if has_incident and seq >= incident_stop:
                                delay += incident_s
                            events.append(
                                StopEvent(
                                    trip=trip,
                                    stop=stop,
                                    sequence=seq,
                                    scheduled_arrival=scheduled,
                                    actual_arrival=scheduled + timedelta(seconds=delay),
                                )
                            )
            StopEvent.objects.bulk_create(events, batch_size=2000)
            total_events += len(events)
            self.stdout.write(f"Route {short}: {len(events)} stop events")

        self.stdout.write(self.style.SUCCESS(f"Created {total_events} stop events."))
