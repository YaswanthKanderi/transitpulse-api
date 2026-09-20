from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("routes", views.RouteViewSet, basename="route")

urlpatterns = [
    path("health/", views.health, name="health"),
    path("", include(router.urls)),
]
