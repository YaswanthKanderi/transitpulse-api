from datetime import timedelta

from django.db import connection
from django.db.models import Count
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from . import analytics
from .models import Route, StopEvent
from .serializers import RouteSerializer


def _int_param(request, name: str, default: int, low: int, high: int) -> int:
    raw = request.query_params.get(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError({name: "must be a whole number"}) from None
    if not low <= value <= high:
        raise ValidationError({name: f"must be between {low} and {high}"})
    return value


@api_view(["GET"])
def health(request):
    """Liveness check that also confirms the database answers."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return Response({"status": "ok"})


class RouteViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Route.objects.annotate(trip_count=Count("trips")).order_by("short_name")
    serializer_class = RouteSerializer
    lookup_field = "short_name"

    def _frame(self, request, route):
        days = _int_param(request, "days", default=30, low=1, high=365)
        since = timezone.now() - timedelta(days=days)
        events = StopEvent.objects.filter(
            trip__route=route, scheduled_arrival__gte=since
        )
        return days, analytics.events_to_frame(events)

    @action(detail=True, methods=["get"])
    def performance(self, request, short_name=None):
        """On-time performance and headway regularity for one route."""
        route = self.get_object()
        days, df = self._frame(request, route)
        return Response(
            {
                "route": route.short_name,
                "window_days": days,
                "on_time": analytics.on_time_performance(df),
                "headway": analytics.headway_summary(df),
            }
        )

    @action(detail=True, methods=["get"], url_path="delay-by-hour")
    def delay_by_hour(self, request, short_name=None):
        route = self.get_object()
        days, df = self._frame(request, route)
        return Response(
            {
                "route": route.short_name,
                "window_days": days,
                "hours": analytics.delay_by_hour(df),
            }
        )

    @action(detail=True, methods=["get"], url_path="worst-stops")
    def worst_stops(self, request, short_name=None):
        route = self.get_object()
        days, df = self._frame(request, route)
        n = _int_param(request, "n", default=5, low=1, high=50)
        return Response(
            {
                "route": route.short_name,
                "window_days": days,
                "stops": analytics.worst_stops(df, n=n),
            }
        )
