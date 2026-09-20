from django.db import models


class Route(models.Model):
    class Mode(models.TextChoices):
        BUS = "bus", "Bus"
        TRAM = "tram", "Tram"
        TRAIN = "train", "Train"

    short_name = models.CharField(max_length=20, unique=True)
    long_name = models.CharField(max_length=120, blank=True)
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.BUS)

    class Meta:
        ordering = ["short_name"]

    def __str__(self) -> str:
        return f"{self.short_name} ({self.mode})"


class Stop(models.Model):
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=120)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class Trip(models.Model):
    """One run of a vehicle along a route in one direction."""

    trip_ref = models.CharField(max_length=60, unique=True)
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="trips")
    direction = models.PositiveSmallIntegerField(default=0)

    def __str__(self) -> str:
        return self.trip_ref


class StopEvent(models.Model):
    """Scheduled versus actual arrival of one trip at one stop."""

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="events")
    stop = models.ForeignKey(Stop, on_delete=models.PROTECT, related_name="events")
    sequence = models.PositiveSmallIntegerField()
    scheduled_arrival = models.DateTimeField(db_index=True)
    actual_arrival = models.DateTimeField()

    class Meta:
        ordering = ["trip_id", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["trip", "sequence"], name="unique_trip_sequence"
            ),
        ]
        indexes = [models.Index(fields=["stop", "scheduled_arrival"])]

    def __str__(self) -> str:
        return f"{self.trip_id} @ {self.stop_id} #{self.sequence}"

    @property
    def delay_seconds(self) -> float:
        return (self.actual_arrival - self.scheduled_arrival).total_seconds()
