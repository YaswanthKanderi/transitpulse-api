from rest_framework import serializers

from .models import Route


class RouteSerializer(serializers.ModelSerializer):
    trip_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Route
        fields = ["short_name", "long_name", "mode", "trip_count"]
