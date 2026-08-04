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
    (
        "Network Events Over Time",
        "search --filter='index=\"network_security\"' --filter='created__gte={last_hour}' "
        "| annotate --set='minute=TruncMinute(created)' "
        "| groupby --keys='[\"minute\"]' --out='event_count' "
        "| sort --fields='[\"minute\"]'",
    ),
    (
        "Network Events by Type",
        "search --filter='index=\"network_security\"' --filter='created__gte={last_hour}' "
        "| groupby --keys='[\"extracted_fields__event_type\"]' --out='event_count' "
        "| rename --mapping='{\"extracted_fields__event_type\": \"event_type\"}' "
        "| sort --fields='[\"-event_count\"]'",
    ),
    (
        "Recent Network Security Events",
        "search --filter='index=\"network_security\"' "
        "--select='[\"created\",\"host\",\"extracted_fields__event_type\","
        "\"extracted_fields__data__protocol\",\"extracted_fields__data__local_address\","
        "\"extracted_fields__data__local_port\",\"extracted_fields__data__remote_address\","
        "\"extracted_fields__data__remote_port\",\"extracted_fields__data__process_name\"]' "
        "--order-by='[\"-created\"]' --limit=100 "
        "| rename --mapping='{\"extracted_fields__event_type\": \"event_type\","
        "\"extracted_fields__data__protocol\": \"protocol\","
        "\"extracted_fields__data__local_address\": \"local_address\","
        "\"extracted_fields__data__local_port\": \"local_port\","
        "\"extracted_fields__data__remote_address\": \"remote_address\","
        "\"extracted_fields__data__remote_port\": \"remote_port\","
        "\"extracted_fields__data__process_name\": \"process_name\"}'",
    ),
    (
        "Network Collection Health",
        "search --filter='index=\"network_security\"' "
        "--filter='extracted_fields__event_type=\"collection_status\"' "
        "--select='[\"created\",\"host\",\"extracted_fields__data__state\","
        "\"extracted_fields__data__listener_count\",\"extracted_fields__data__connection_count\","
        "\"extracted_fields__data__processes_access_denied\","
        "\"extracted_fields__data__processes_unavailable\","
        "\"extracted_fields__data__collection_duration_ms\"]' "
        "--order-by='[\"-created\"]' --limit=50 "
        "| rename --mapping='{\"extracted_fields__data__state\": \"state\","
        "\"extracted_fields__data__listener_count\": \"listener_count\","
        "\"extracted_fields__data__connection_count\": \"connection_count\","
        "\"extracted_fields__data__processes_access_denied\": \"processes_access_denied\","
        "\"extracted_fields__data__processes_unavailable\": \"processes_unavailable\","
        "\"extracted_fields__data__collection_duration_ms\": \"collection_duration_ms\"}'",
    ),
    (
        "Listener Activity by Process",
        "search --filter='index=\"network_security\"' --filter='created__gte={last_day}' "
        "--filter='extracted_fields__event_type=\"listener_added\"' "
        "| groupby --keys='[\"extracted_fields__data__process_name\"]' --out='event_count' "
        "| rename --mapping='{\"extracted_fields__data__process_name\": \"process_name\"}' "
        "| sort --fields='[\"-event_count\"]' | head --n=15",
    ),
    (
        "Listener Activity by Port",
        "search --filter='index=\"network_security\"' --filter='created__gte={last_day}' "
        "--filter='extracted_fields__event_type=\"listener_added\"' "
        "| groupby --keys='[\"extracted_fields__data__local_port\"]' --out='event_count' "
        "| rename --mapping='{\"extracted_fields__data__local_port\": \"local_port\"}' "
        "| sort --fields='[\"-event_count\"]' | head --n=15",
    ),
    (
        "Recent Listener Activity",
        "search --filter='index=\"network_security\"' "
        "--filter='extracted_fields__event_type__in=[\"listener_added\",\"listener_removed\",\"listener_changed\"]' "
        "--select='[\"created\",\"host\",\"extracted_fields__event_type\","
        "\"extracted_fields__data__protocol\",\"extracted_fields__data__local_address\","
        "\"extracted_fields__data__local_port\",\"extracted_fields__data__local_scope\","
        "\"extracted_fields__data__pid\",\"extracted_fields__data__process_name\","
        "\"extracted_fields__data__process_user\"]' --order-by='[\"-created\"]' --limit=100 "
        "| rename --mapping='{\"extracted_fields__event_type\": \"event_type\","
        "\"extracted_fields__data__protocol\": \"protocol\","
        "\"extracted_fields__data__local_address\": \"local_address\","
        "\"extracted_fields__data__local_port\": \"local_port\","
        "\"extracted_fields__data__local_scope\": \"local_scope\","
        "\"extracted_fields__data__pid\": \"pid\","
        "\"extracted_fields__data__process_name\": \"process_name\","
        "\"extracted_fields__data__process_user\": \"process_user\"}'",
    ),
    (
        "Wildcard Listener Activity",
        "search --filter='index=\"network_security\"' "
        "--filter='extracted_fields__event_type__in=[\"listener_added\",\"listener_removed\",\"listener_changed\"]' "
        "--filter='extracted_fields__data__local_scope=\"wildcard\"' "
        "--select='[\"created\",\"host\",\"extracted_fields__event_type\","
        "\"extracted_fields__data__protocol\",\"extracted_fields__data__local_address\","
        "\"extracted_fields__data__local_port\",\"extracted_fields__data__pid\","
        "\"extracted_fields__data__process_name\",\"extracted_fields__data__process_exe\"]' "
        "--order-by='[\"-created\"]' --limit=100 "
        "| rename --mapping='{\"extracted_fields__event_type\": \"event_type\","
        "\"extracted_fields__data__protocol\": \"protocol\","
        "\"extracted_fields__data__local_address\": \"local_address\","
        "\"extracted_fields__data__local_port\": \"local_port\","
        "\"extracted_fields__data__pid\": \"pid\","
        "\"extracted_fields__data__process_name\": \"process_name\","
        "\"extracted_fields__data__process_exe\": \"process_exe\"}'",
    ),
    (
        "Public Connections by Process",
        "search --filter='index=\"network_security\"' --filter='created__gte={last_hour}' "
        "--filter='extracted_fields__event_type=\"connection_opened\"' "
        "--filter='extracted_fields__data__remote_scope=\"public\"' "
        "| groupby --keys='[\"extracted_fields__data__process_name\"]' --out='event_count' "
        "| rename --mapping='{\"extracted_fields__data__process_name\": \"process_name\"}' "
        "| sort --fields='[\"-event_count\"]' | head --n=15",
    ),
    (
        "Public Connections by Destination Port",
        "search --filter='index=\"network_security\"' --filter='created__gte={last_hour}' "
        "--filter='extracted_fields__event_type=\"connection_opened\"' "
        "--filter='extracted_fields__data__remote_scope=\"public\"' "
        "| groupby --keys='[\"extracted_fields__data__remote_port\"]' --out='event_count' "
        "| rename --mapping='{\"extracted_fields__data__remote_port\": \"remote_port\"}' "
        "| sort --fields='[\"-event_count\"]' | head --n=15",
    ),
    (
        "Public Connections by Remote Address",
        "search --filter='index=\"network_security\"' --filter='created__gte={last_hour}' "
        "--filter='extracted_fields__event_type=\"connection_opened\"' "
        "--filter='extracted_fields__data__remote_scope=\"public\"' "
        "| groupby --keys='[\"extracted_fields__data__remote_address\"]' --out='event_count' "
        "| rename --mapping='{\"extracted_fields__data__remote_address\": \"remote_address\"}' "
        "| sort --fields='[\"-event_count\"]' | head --n=15",
    ),
    (
        "Recent Public Connections",
        "search --filter='index=\"network_security\"' "
        "--filter='extracted_fields__event_type__in=[\"connection_opened\",\"connection_closed\",\"connection_changed\"]' "
        "--filter='extracted_fields__data__remote_scope=\"public\"' "
        "--select='[\"created\",\"host\",\"extracted_fields__event_type\","
        "\"extracted_fields__data__protocol\",\"extracted_fields__data__local_address\","
        "\"extracted_fields__data__local_port\",\"extracted_fields__data__remote_address\","
        "\"extracted_fields__data__remote_port\",\"extracted_fields__data__status\","
        "\"extracted_fields__data__pid\",\"extracted_fields__data__process_name\"]' "
        "--order-by='[\"-created\"]' --limit=100 "
        "| rename --mapping='{\"extracted_fields__event_type\": \"event_type\","
        "\"extracted_fields__data__protocol\": \"protocol\","
        "\"extracted_fields__data__local_address\": \"local_address\","
        "\"extracted_fields__data__local_port\": \"local_port\","
        "\"extracted_fields__data__remote_address\": \"remote_address\","
        "\"extracted_fields__data__remote_port\": \"remote_port\","
        "\"extracted_fields__data__status\": \"status\","
        "\"extracted_fields__data__pid\": \"pid\","
        "\"extracted_fields__data__process_name\": \"process_name\"}'",
    ),
    (
        "Host Posture Events Over Time",
        "search --filter='index=\"host_security_posture\"' --filter='created__gte={last_7_days}' "
        "| annotate --set='hour=TruncHour(created)' "
        "| groupby --keys='[\"hour\"]' --out='event_count' "
        "| sort --fields='[\"hour\"]'",
    ),
    (
        "Host Posture Events by Component",
        "search --filter='index=\"host_security_posture\"' --filter='created__gte={last_7_days}' "
        "--exclude='extracted_fields__component=\"collector\"' "
        "| groupby --keys='[\"extracted_fields__component\"]' --out='event_count' "
        "| rename --mapping='{\"extracted_fields__component\": \"component\"}' "
        "| sort --fields='[\"-event_count\"]'",
    ),
    (
        "Recent Host Posture Events",
        "search --filter='index=\"host_security_posture\"' "
        "--select='[\"created\",\"host\",\"extracted_fields__event_type\","
        "\"extracted_fields__component\",\"extracted_fields__data\"]' "
        "--order-by='[\"-created\"]' --limit=100 "
        "| rename --mapping='{\"extracted_fields__event_type\": \"event_type\","
        "\"extracted_fields__component\": \"component\","
        "\"extracted_fields__data\": \"posture_data\"}'",
    ),
    (
        "Host Posture Collection Health",
        "search --filter='index=\"host_security_posture\"' "
        "--filter='extracted_fields__event_type=\"collection_status\"' "
        "--select='[\"created\",\"host\",\"extracted_fields__data__state\","
        "\"extracted_fields__data__components_collected\","
        "\"extracted_fields__data__components_failed\","
        "\"extracted_fields__data__issues\","
        "\"extracted_fields__data__collection_duration_ms\"]' "
        "--order-by='[\"-created\"]' --limit=50 "
        "| rename --mapping='{\"extracted_fields__data__state\": \"state\","
        "\"extracted_fields__data__components_collected\": \"components_collected\","
        "\"extracted_fields__data__components_failed\": \"components_failed\","
        "\"extracted_fields__data__issues\": \"issues\","
        "\"extracted_fields__data__collection_duration_ms\": \"collection_duration_ms\"}'",
    ),
    (
        "Security Control Events by Host",
        "search --filter='index=\"host_security_posture\"' --filter='created__gte={last_7_days}' "
        "--filter='extracted_fields__component=\"security_controls\"' "
        "| groupby --keys='[\"host\"]' --out='event_count' "
        "| sort --fields='[\"-event_count\"]'",
    ),
    (
        "Security Control Activity Over Time",
        "search --filter='index=\"host_security_posture\"' --filter='created__gte={last_7_days}' "
        "--filter='extracted_fields__component=\"security_controls\"' "
        "| annotate --set='hour=TruncHour(created)' "
        "| groupby --keys='[\"hour\"]' --out='event_count' "
        "| sort --fields='[\"hour\"]'",
    ),
    (
        "Latest Security Control Posture",
        "search --filter='index=\"host_security_posture\"' "
        "--filter='extracted_fields__component=\"security_controls\"' "
        "--select='[\"created\",\"host\",\"extracted_fields__event_type\","
        "\"extracted_fields__data__firewall__state\","
        "\"extracted_fields__data__firewall__profiles\","
        "\"extracted_fields__data__secure_boot__state\","
        "\"extracted_fields__data__secure_boot__enabled\","
        "\"extracted_fields__data__disk_encryption__provider\","
        "\"extracted_fields__data__disk_encryption__state\","
        "\"extracted_fields__data__disk_encryption__volumes\","
        "\"extracted_fields__data__endpoint_protection__provider\","
        "\"extracted_fields__data__endpoint_protection__state\","
        "\"extracted_fields__data__endpoint_protection__realtime_protection_enabled\","
        "\"extracted_fields__data__gatekeeper__enabled\"]' "
        "--order-by='[\"-created\"]' --limit=50 "
        "| rename --mapping='{\"extracted_fields__event_type\": \"event_type\","
        "\"extracted_fields__data__firewall__state\": \"firewall_state\","
        "\"extracted_fields__data__firewall__profiles\": \"firewall_profiles\","
        "\"extracted_fields__data__secure_boot__state\": \"secure_boot_state\","
        "\"extracted_fields__data__secure_boot__enabled\": \"secure_boot_enabled\","
        "\"extracted_fields__data__disk_encryption__provider\": \"encryption_provider\","
        "\"extracted_fields__data__disk_encryption__state\": \"encryption_state\","
        "\"extracted_fields__data__disk_encryption__volumes\": \"encrypted_volumes\","
        "\"extracted_fields__data__endpoint_protection__provider\": \"protection_provider\","
        "\"extracted_fields__data__endpoint_protection__state\": \"protection_state\","
        "\"extracted_fields__data__endpoint_protection__realtime_protection_enabled\": \"realtime_protection\","
        "\"extracted_fields__data__gatekeeper__enabled\": \"gatekeeper_enabled\"}'",
    ),
    (
        "Security Control Change History",
        "search --filter='index=\"host_security_posture\"' "
        "--filter='extracted_fields__component=\"security_controls\"' "
        "--filter='extracted_fields__event_type=\"posture_changed\"' "
        "--select='[\"created\",\"host\",\"extracted_fields__data\","
        "\"extracted_fields__previous\"]' --order-by='[\"-created\"]' --limit=100 "
        "| rename --mapping='{\"extracted_fields__data\": \"current_controls\","
        "\"extracted_fields__previous\": \"previous_controls\"}'",
    ),
    (
        "Latest Host Identity",
        "search --filter='index=\"host_security_posture\"' "
        "--filter='extracted_fields__component=\"host_identity\"' "
        "--select='[\"created\",\"host\",\"extracted_fields__data__fqdn\","
        "\"extracted_fields__data__os\",\"extracted_fields__data__os_release\","
        "\"extracted_fields__data__architecture\",\"extracted_fields__data__boot_time\","
        "\"extracted_fields__data__timezone\",\"extracted_fields__data__agent_user\","
        "\"extracted_fields__data__agent_privileged\"]' "
        "--order-by='[\"-created\"]' --limit=50 "
        "| rename --mapping='{\"extracted_fields__data__fqdn\": \"fqdn\","
        "\"extracted_fields__data__os\": \"os\","
        "\"extracted_fields__data__os_release\": \"os_release\","
        "\"extracted_fields__data__architecture\": \"architecture\","
        "\"extracted_fields__data__boot_time\": \"boot_time\","
        "\"extracted_fields__data__timezone\": \"timezone\","
        "\"extracted_fields__data__agent_user\": \"agent_user\","
        "\"extracted_fields__data__agent_privileged\": \"agent_privileged\"}'",
    ),
    (
        "Latest Local Account Inventory",
        "search --filter='index=\"host_security_posture\"' "
        "--filter='extracted_fields__component=\"local_accounts\"' "
        "--select='[\"created\",\"host\",\"extracted_fields__event_type\","
        "\"extracted_fields__data\"]' --order-by='[\"-created\"]' --limit=25 "
        "| rename --mapping='{\"extracted_fields__event_type\": \"event_type\","
        "\"extracted_fields__data\": \"local_accounts\"}'",
    ),
    (
        "Latest User Session Inventory",
        "search --filter='index=\"host_security_posture\"' "
        "--filter='extracted_fields__component=\"user_sessions\"' "
        "--select='[\"created\",\"host\",\"extracted_fields__event_type\","
        "\"extracted_fields__data\"]' --order-by='[\"-created\"]' --limit=25 "
        "| rename --mapping='{\"extracted_fields__event_type\": \"event_type\","
        "\"extracted_fields__data\": \"user_sessions\"}'",
    ),
    (
        "Latest Network Interface Inventory",
        "search --filter='index=\"host_security_posture\"' "
        "--filter='extracted_fields__component=\"network_interfaces\"' "
        "--select='[\"created\",\"host\",\"extracted_fields__event_type\","
        "\"extracted_fields__data\"]' --order-by='[\"-created\"]' --limit=25 "
        "| rename --mapping='{\"extracted_fields__event_type\": \"event_type\","
        "\"extracted_fields__data\": \"network_interfaces\"}'",
    ),
    (
        "Latest Filesystem Inventory",
        "search --filter='index=\"host_security_posture\"' "
        "--filter='extracted_fields__component=\"filesystems\"' "
        "--select='[\"created\",\"host\",\"extracted_fields__event_type\","
        "\"extracted_fields__data\"]' --order-by='[\"-created\"]' --limit=25 "
        "| rename --mapping='{\"extracted_fields__event_type\": \"event_type\","
        "\"extracted_fields__data\": \"filesystems\"}'",
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
    (
        "Network Security Overview",
        "Recent network-collector activity, including event volume, event types, "
        "and collection health. Counts describe observed changes, not a current-"
        "state port scan.",
        [
            ("Network Events Over Time", "Network Events Over Time", "chart", "line", "minute", "event_count"),
            ("Network Events by Type", "Network Events by Type", "chart", "bar", "event_type", "event_count"),
            ("Recent Network Security Events", "Recent Network Security Events", "table", None, None, None),
            ("Network Collection Health", "Network Collection Health", "table", None, None, None),
        ],
    ),
    (
        "Listening Service Activity",
        "Listener additions, removals, and changes observed by the agent. "
        "Wildcard binds deserve special review because they accept traffic on "
        "every matching interface.",
        [
            ("Listener Discoveries by Process", "Listener Activity by Process", "chart", "bar", "process_name", "event_count"),
            ("Listener Discoveries by Port", "Listener Activity by Port", "chart", "bar", "local_port", "event_count"),
            ("Wildcard Listener Activity", "Wildcard Listener Activity", "table", None, None, None),
            ("Recent Listener Activity", "Recent Listener Activity", "table", None, None, None),
        ],
    ),
    (
        "Public Connection Activity",
        "Connections to publicly routable remote addresses observed during the "
        "selected collection windows. Use the tables to pivot from destinations "
        "to the responsible process and PID.",
        [
            ("Public Connections by Process", "Public Connections by Process", "chart", "bar", "process_name", "event_count"),
            ("Public Connections by Destination Port", "Public Connections by Destination Port", "chart", "bar", "remote_port", "event_count"),
            ("Top Public Remote Addresses", "Public Connections by Remote Address", "chart", "bar", "remote_address", "event_count"),
            ("Recent Public Connections", "Recent Public Connections", "table", None, None, None),
        ],
    ),
    (
        "Host Security Posture Overview",
        "Host posture snapshots, detected changes, and collector health. Event "
        "counts represent inventory activity and should not be read as a count "
        "of current vulnerabilities.",
        [
            ("Posture Events Over Time", "Host Posture Events Over Time", "chart", "line", "hour", "event_count"),
            ("Posture Events by Component", "Host Posture Events by Component", "chart", "bar", "component", "event_count"),
            ("Recent Host Posture Events", "Recent Host Posture Events", "table", None, None, None),
            ("Posture Collection Health", "Host Posture Collection Health", "table", None, None, None),
        ],
    ),
    (
        "Security Controls & Encryption",
        "Best-effort firewall, secure-boot, disk-encryption, endpoint-protection, "
        "and macOS Gatekeeper posture. An unknown state can indicate unsupported "
        "hardware, a missing platform tool, or insufficient privileges.",
        [
            ("Security Control Activity Over Time", "Security Control Activity Over Time", "chart", "line", "hour", "event_count"),
            ("Security Control Events by Host", "Security Control Events by Host", "chart", "bar", "host", "event_count"),
            ("Latest Security Control Posture", "Latest Security Control Posture", "table", None, None, None),
            ("Security Control Change History", "Security Control Change History", "table", None, None, None),
        ],
    ),
    (
        "Host Identity & Access Inventory",
        "Host identity and the latest collected account, session, interface, and "
        "filesystem inventories. Inventory cells retain structured lists so no "
        "platform-specific fields are discarded.",
        [
            ("Latest Host Identity", "Latest Host Identity", "table", None, None, None),
            ("Latest Local Accounts", "Latest Local Account Inventory", "table", None, None, None),
            ("Latest User Sessions", "Latest User Session Inventory", "table", None, None, None),
            ("Latest Network Interfaces", "Latest Network Interface Inventory", "table", None, None, None),
            ("Latest Filesystems", "Latest Filesystem Inventory", "table", None, None, None),
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
