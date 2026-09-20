# TransitPulse

A Django REST API that loads bus and tram stop-arrival data, checks it for
quality problems, and reports service reliability: on-time performance, delay
by hour, worst stops, and vehicle bunching. Analytics run in pandas, the API
runs on Django REST Framework, and the whole thing ships in Docker with a
GitHub Actions pipeline.

The data is synthetic. I built it to practise the shape of a transport
analytics backend (ingest, validate, analyse, serve, deploy), not to publish
real service statistics.

## What it does

- **Ingests CSV** stop events with row-level validation. Bad rows are rejected
  with a line number and a reason, good rows still load, and re-running the
  same file creates no duplicates.
- **Computes reliability metrics** with pandas from scheduled versus actual
  arrival times.
- **Serves them over a JSON API** with input validation and proper status codes.
- **Generates reproducible sample data** (seeded) so anyone can run the demo.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

python manage.py migrate
python manage.py generate_sample_data --days 14
python manage.py runserver
```

Then open `http://127.0.0.1:8000/api/routes/`.

With Docker (PostgreSQL + gunicorn):

```bash
docker compose up --build
docker compose exec web python manage.py generate_sample_data --days 14
```

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health/` | Liveness check that also queries the database |
| `GET /api/routes/` | Routes with trip counts (paginated) |
| `GET /api/routes/{route}/performance/?days=30` | On-time, early and late share, mean and 90th percentile delay, headway error, bunching |
| `GET /api/routes/{route}/delay-by-hour/?days=30` | Mean delay and on-time share for each hour of the day |
| `GET /api/routes/{route}/worst-stops/?days=30&n=5` | Stops with the highest mean delay |

Example response for `/api/routes/96/performance/` on the seeded sample data:

```json
{
  "route": "96",
  "window_days": 30,
  "on_time": {
    "events": 13440,
    "on_time_pct": 96.0,
    "early_pct": 0.0,
    "late_pct": 4.0,
    "mean_delay_s": 148.0,
    "p90_delay_s": 254.2
  },
  "headway": {
    "headways_measured": 13300,
    "mean_headway_error_s": 74.0,
    "bunching_pct": 1.2
  }
}
```

Bad input returns a 400 with the field name (`?days=abc`, `?days=999`), and an
unknown route returns a 404.

## Loading your own data

```bash
python manage.py ingest_csv sample_data/events_sample.csv
```

Required columns: `trip_ref, route, direction, stop_code, sequence,
scheduled_arrival, actual_arrival` (ISO 8601 timestamps). The sample file has
two deliberately broken rows, so you can see the rejection report:

```
Created 8, skipped 0 duplicates, rejected 2 rows.
  line 10: direction must be 0 or 1, got 5
  line 11: delay is more than 6 hours, likely a timestamp fault
```

## How the metrics are defined

- **On time** means arriving no more than 60 seconds early and no more than
  300 seconds late. Both limits are settings (`ON_TIME_EARLY_S`,
  `ON_TIME_LATE_S`).
- **Headway error** is the average gap between the scheduled spacing of two
  consecutive vehicles at a stop and their actual spacing.
- **Bunching** is the share of headways where the actual gap was under 25% of
  the scheduled gap.
- Headways over 30 minutes are skipped. On infrequent services the timetable
  matters more than spacing, and the gap between the last trip of one day and
  the first of the next would distort the average.
- `worst-stops` ignores stops with fewer than 5 observations so a single bad
  day at a quiet stop does not top the list.

## Project layout

```
config/                  settings, urls, wsgi
transit/models.py        Route, Stop, Trip, StopEvent
transit/analytics.py     pandas metrics (pure functions, no database needed)
transit/ingest.py        row validation and idempotent loading
transit/views.py         API endpoints and query parameter checks
transit/management/      generate_sample_data and ingest_csv commands
transit/tests/           analytics, ingest, API and sample data tests
.github/workflows/       CI: lint, migration check, tests, Docker build
```

## Design decisions

- **Analytics are separate from the database.** `analytics.py` takes a
  DataFrame, so each metric is tested with a small hand-built table where I can
  work out the right answer by hand.
- **Ingestion never fails the whole file for one bad row.** Feeds are messy.
  The load reports what it rejected and why, inside one transaction.
- **A delay over 6 hours is rejected** as a probable timestamp or timezone
  fault, rather than being allowed to drag the averages.
- **SQLite for development, PostgreSQL in Docker.** The switch is one
  environment variable (`POSTGRES_HOST`).
- **Timestamps are stored in UTC** and converted to Melbourne time only when
  grouping by hour of day.

## Tests and CI

```bash
pytest --cov=transit
ruff check . && ruff format --check .
```

The suite covers the metrics against known answers, every validation rule,
idempotent ingestion, API status codes and error messages, and reproducible
sample data. CI runs lint, checks for missing migrations, runs the tests with a
coverage floor of 85%, and builds the Docker image.

## Limitations and next steps

- The sample data comes from a simple model (route bias, rush-hour penalty,
  drift along the route, random noise, occasional incidents). It is not a real
  timetable.
- No authentication or rate limiting on the API.
- Analytics load the filtered events into memory. That is fine for hundreds of
  thousands of rows. Beyond that I would push the aggregation into SQL or a
  batch job.
- Next: a GTFS static and GTFS-realtime importer, a scheduled ingest job, and
  a small dashboard on top of the API.
