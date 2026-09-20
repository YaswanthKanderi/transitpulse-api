import pytest
from rest_framework.test import APIClient


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
def test_health_endpoint(client):
    response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_route_list_includes_trip_count(client, route, stop, make_event):
    make_event(route, stop, 0)
    make_event(route, stop, 0)
    data = client.get("/api/routes/").json()
    assert data["count"] == 1
    assert data["results"][0]["short_name"] == "96"
    assert data["results"][0]["trip_count"] == 2


def test_performance_endpoint_returns_expected_numbers(client, route, stop, make_event):
    for delay in (0, 30, 400, -200):
        make_event(route, stop, delay)
    data = client.get("/api/routes/96/performance/").json()
    assert data["on_time"]["events"] == 4
    assert data["on_time"]["on_time_pct"] == 50.0
    assert data["on_time"]["late_pct"] == 25.0
    assert data["on_time"]["early_pct"] == 25.0


def test_performance_with_no_data_is_not_an_error(client, route):
    data = client.get("/api/routes/96/performance/").json()
    assert data["on_time"]["events"] == 0
    assert data["on_time"]["on_time_pct"] is None


def test_unknown_route_returns_404(client, db):
    assert client.get("/api/routes/nope/performance/").status_code == 404


@pytest.mark.parametrize("query", ["days=abc", "days=0", "days=999"])
def test_invalid_days_returns_400(client, route, query):
    response = client.get(f"/api/routes/96/performance/?{query}")
    assert response.status_code == 400
    assert "days" in response.json()


def test_worst_stops_respects_n(client, route, make_event, db):
    from transit.models import Stop

    for i in range(3):
        stop = Stop.objects.create(code=f"X{i}", name=f"Stop {i}")
        for _ in range(5):
            make_event(route, stop, delay_s=100 * (i + 1))
    data = client.get("/api/routes/96/worst-stops/?n=2").json()
    assert [s["stop_code"] for s in data["stops"]] == ["X2", "X1"]
