"""Load stop events from a CSV file with validation.

Usage: python manage.py ingest_csv path/to/events.csv
"""

import csv

from django.core.management.base import BaseCommand, CommandError

from transit.ingest import REQUIRED_COLUMNS, ingest_rows


class Command(BaseCommand):
    help = "Validate and load stop events from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument("path")

    def handle(self, *args, path, **options):
        try:
            handle = open(path, newline="", encoding="utf-8")
        except OSError as exc:
            raise CommandError(f"Cannot open {path}: {exc}") from exc

        with handle:
            reader = csv.DictReader(handle)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise CommandError(
                    f"CSV is missing columns: {', '.join(sorted(missing))}"
                )
            result = ingest_rows(reader)

        self.stdout.write(
            f"Created {result.created}, skipped {result.skipped_duplicates} "
            f"duplicates, rejected {len(result.rejected)} rows."
        )
        for line_no, reason in result.rejected[:20]:
            self.stderr.write(f"  line {line_no}: {reason}")
        if len(result.rejected) > 20:
            self.stderr.write(f"  ... and {len(result.rejected) - 20} more")
