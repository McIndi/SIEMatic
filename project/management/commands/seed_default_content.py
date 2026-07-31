"""Seed the default saved searches and dashboards that ship with rundev.

Idempotent: existing rows (matched by owner/name) are left untouched, so a
developer's edits to these defaults survive repeated ``rundev`` runs.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from dashboarding.models import Dashboard, Panel
from search2.models import SavedSearch


# Field paths use only metrics psutil reports the same way on every OS
# (cpu_percent, memory.percent). Disk usage is deliberately left out of the
# defaults: psutil keys the `disk` dict by mount point, which is a drive
# letter on Windows (e.g. "C:\\") and a POSIX path elsewhere, so a single
# saved search referencing a specific key isn't portable across hosts.
SAVED_SEARCHES = [
    (
        "Recent Events",
        "search --order-by='[\"-created\"]' --limit=100",
    ),
    (
        "Recent System Metrics",
        "search --filter='index=\"sysmon\"' "
        "--select='[\"created\",\"host\",\"extracted_fields__metrics__cpu_percent\",\"extracted_fields__metrics__memory__percent\"]' "
        "--order-by='[\"-created\"]' --limit=100 "
        "| rename --mapping='{\"extracted_fields__metrics__cpu_percent\": \"cpu_percent\", "
        "\"extracted_fields__metrics__memory__percent\": \"memory_percent\"}'",
    ),
    (
        "Recent Agent Heartbeats",
        "search --filter='index=\"default\"' --order-by='[\"-created\"]' --limit=100",
    ),
    (
        "Event Volume by Index",
        "search | groupby --keys='[\"index\"]' --out='event_count'",
    ),
    (
        "Hosts Reporting",
        "search --filter='index=\"sysmon\"' | groupby --keys='[\"host\"]' --out='event_count'",
    ),
    (
        "Average CPU Percent by Host",
        "search --filter='index=\"sysmon\"' "
        "| groupby --keys='[\"host\", \"Avg(extracted_fields__metrics__cpu_percent)\"]' --out='avg_cpu_percent'",
    ),
    (
        "Average Memory Percent by Host",
        "search --filter='index=\"sysmon\"' "
        "| groupby --keys='[\"host\", \"Avg(extracted_fields__metrics__memory__percent)\"]' --out='avg_memory_percent'",
    ),
    (
        "Average CPU Percent Over Time",
        "search --filter='index=\"sysmon\"' --filter='created__gte={last_hour}' "
        "| annotate --set='minute=TruncMinute(created)' "
        "| groupby --keys='[\"minute\", \"Avg(extracted_fields__metrics__cpu_percent)\"]' --out='avg_cpu_percent' "
        "| sort --fields='[\"minute\"]'",
    ),
    (
        "Average Memory Percent Over Time",
        "search --filter='index=\"sysmon\"' --filter='created__gte={last_hour}' "
        "| annotate --set='minute=TruncMinute(created)' "
        "| groupby --keys='[\"minute\", \"Avg(extracted_fields__metrics__memory__percent)\"]' --out='avg_memory_percent' "
        "| sort --fields='[\"minute\"]'",
    ),
    (
        "Event Volume Over Time",
        "search --filter='created__gte={last_hour}' "
        "| annotate --set='minute=TruncMinute(created)' "
        "| groupby --keys='[\"minute\"]' "
        "| sort --fields='[\"minute\"]'",
    ),
    (
        "High CPU Usage",
        "search --filter='index=\"sysmon\"' --filter='extracted_fields__metrics__cpu_percent__gte=80' "
        "--order-by='[\"-created\"]' --limit=100",
    ),
]

DASHBOARDS = [
    (
        "System Health Overview",
        "CPU and memory usage collected by the sysmon agent plugin (psutil-based "
        "system metrics, not Microsoft Sysinternals Sysmon). Disk usage is host- "
        "and OS-specific and isn't included in these defaults.",
        [
            ("Average CPU % Over Time", "Average CPU Percent Over Time", "chart", "line", "minute", "avg_cpu_percent"),
            ("Average Memory % Over Time", "Average Memory Percent Over Time", "chart", "line", "minute", "avg_memory_percent"),
            ("Average CPU % by Host", "Average CPU Percent by Host", "chart", "bar", "host", "avg_cpu_percent"),
            ("Average Memory % by Host", "Average Memory Percent by Host", "chart", "bar", "host", "avg_memory_percent"),
            ("Recent System Metrics", "Recent System Metrics", "table", None, None, None),
        ],
    ),
    (
        "Agent & Ingestion Health",
        "Event throughput and reporting hosts, for confirming the agent and "
        "indexer are alive and ingesting.",
        [
            ("Event Volume Over Time", "Event Volume Over Time", "chart", "line", "minute", "count"),
            ("Event Volume by Index", "Event Volume by Index", "chart", "bar", "index", "event_count"),
            ("Hosts Reporting", "Hosts Reporting", "chart", "bar", "host", "event_count"),
            ("Recent Agent Heartbeats", "Recent Agent Heartbeats", "table", None, None, None),
        ],
    ),
]


class Command(BaseCommand):
    help = "Seed the default saved searches and dashboards that ship with rundev."

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner",
            default="siematic-admin",
            help="Username that owns the seeded saved searches and dashboards (default: siematic-admin)",
        )

    def handle(self, *args, **options):
        user_model = get_user_model()
        try:
            owner = user_model.objects.get(username=options["owner"])
        except user_model.DoesNotExist:
            raise CommandError(f"User '{options['owner']}' does not exist; create it before seeding.")

        created_searches = 0
        for name, query in SAVED_SEARCHES:
            _, created = SavedSearch.objects.get_or_create(
                owner=owner,
                name=name,
                defaults={"query": query, "is_public": True},
            )
            created_searches += created

        created_dashboards = 0
        for name, description, panels in DASHBOARDS:
            dashboard, created = Dashboard.objects.get_or_create(
                created_by=owner,
                name=name,
                defaults={"description": description},
            )
            if not created:
                continue
            created_dashboards += 1
            for order, (title, search_name, viz_type, chart_type, x_field, y_field) in enumerate(panels):
                Panel.objects.create(
                    dashboard=dashboard,
                    title=title,
                    search=f'run_saved_search "{search_name}"',
                    visualization_type=viz_type,
                    chart_type=chart_type,
                    x_field=x_field,
                    y_field=y_field,
                    order=order,
                )

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {created_searches} new saved search(es) and {created_dashboards} new dashboard(s) "
            f"for {owner.username}."
        ))
