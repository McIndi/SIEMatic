import logging
import shlex, argparse
from dataclasses import dataclass
from typing import Any, List, Optional

from django.conf import settings
from django.utils import timezone

from ..apps import get_command
from .context import Context


logger = logging.getLogger(__name__)

# Placeholders supplied by the pipeline engine for every query.  Callers that
# collect user-defined parameters should not present or override these fields.
PIPELINE_BUILTIN_FIELDS = frozenset({
    'now',
    'today',
    'yesterday',
    'this_minute',
    'last_minute',
    'this_hour',
    'last_hour',
    'this_day',
    'last_day',
    'this_week',
    'last_week',
    'this_month',
    'last_month',
    'this_year',
    'last_year',
    'last_7_days',
    'last_30_days',
    'timezone',
})

@dataclass
class Stage:
    cmd: str
    argv: List[str]

def parse_pipeline(query: str) -> List[Stage]:
    parts = [p.strip() for p in query.split("|") if p.strip()]
    return [Stage(cmd=shlex.split(p)[0], argv=shlex.split(p)[1:]) for p in parts]

def detect_kind(data: Any) -> Optional[str]:
    if data is None:
        return None
    if hasattr(data, "model") and hasattr(data, "values"):
        return "qs"
    clsname = getattr(getattr(data, "__class__", None), "__name__", "")
    if clsname in ("DataFrame", "Series"):
        return "df"
    if isinstance(data, list) and (not data or isinstance(data[0], dict)):
        return "records"
    raise TypeError(f"Unsupported dataset type: {type(data)}")

class PipelineArgumentError(Exception):
    """Raised for a pipeline stage's invalid arguments, in place of argparse's default
    behavior of printing usage and calling ``sys.exit()``. A ``SystemExit`` raised while
    handling a request is not caught by an ``except Exception`` in a view, so it would
    otherwise propagate out of the request thread and take the whole server down.
    """


class _PipelineArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise PipelineArgumentError(f"{self.format_usage()}{self.prog}: error: {message}")


def _mk_parser(cmd_obj):
    p = _PipelineArgumentParser(prog=cmd_obj.name, add_help=False)
    cmd_obj.add_arguments(p)
    return p

def run_pipeline(data: Any, query: str, *, request=None, environ=None) -> Any:
    logger.info("Starting pipeline with query: %s", query)
    ctx = Context(request=request)
    logger.debug("Running pipeline: %s with initial data type: %s", query, type(data))
    kind = detect_kind(data)
    logger.debug("Detected initial data kind: %s", kind)
    current = data
    now = timezone.now()
    environ = {
        'now': now,
        'today': now.date(),
        'yesterday': (now.date() - timezone.timedelta(days=1)),
        'this_minute': now.replace(second=0, microsecond=0),
        'last_minute': (now - timezone.timedelta(minutes=1)).replace(second=0, microsecond=0),
        'this_hour': now.replace(minute=0, second=0, microsecond=0),
        'last_hour': (now - timezone.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0),
        'this_day': now.replace(hour=0, minute=0, second=0, microsecond=0),
        'last_day': (now - timezone.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
        'this_week': (now - timezone.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0),
        'last_week': (now - timezone.timedelta(days=now.weekday() + 7)).replace(hour=0, minute=0, second=0, microsecond=0),
        'this_month': now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
        'last_month': (now.replace(day=1) - timezone.timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0),
        'this_year': now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
        'last_year': (now.replace(month=1, day=1) - timezone.timedelta(days=1)).replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
        'last_7_days': now - timezone.timedelta(days=7),
        'last_30_days': now - timezone.timedelta(days=30),
        'timezone': timezone.get_current_timezone_name(),
        **(environ or {}),
    }
    for stage in parse_pipeline(query):
        logger.debug("Processing stage: %s %s", stage.cmd, stage.argv)
        cmd = get_command(stage.cmd)
        logger.debug("Using command class: %s", cmd.__class__.__name__)
        parser = _mk_parser(cmd)
        for i, argv in enumerate(stage.argv):
            stripped_argv = argv.strip()
            argument_value = stripped_argv.partition("=")[2] or stripped_argv
            is_mapping_literal = (
                argument_value.startswith(('{"', "{'"))
                and argument_value.endswith("}")
            )
            if not is_mapping_literal:
                stage.argv[i] = argv.format(**environ)
        logger.debug("Parsing arguments: %s", stage.argv)
        args = parser.parse_args(stage.argv)
        logger.debug("Parsed arguments: %s", args)
        method = {"qs": "run_qs", "df": "run_df", "records": "run_records", None: "run_none"}[kind]
        logger.debug("Using method: %s for kind: %s", method, kind)
        if not hasattr(cmd, method):
            logger.exception("Command %s does not support method %s", cmd.__class__.__name__, method)
            raise NotImplementedError(f"{cmd.__class__.__name__} does not support dataset type '{kind}'")
        current = getattr(cmd, method)(current, args, ctx)
        logger.debug("Stage result type: %s", type(current))
        try:
            kind = detect_kind(current)
        except Exception as e:
            logger.exception("Failed to detect kind after stage: %s", e)
            kind = None
    logger.info("Pipeline completed. Final result type: %s", type(current))
    max_rows = getattr(settings, "SIEMATIC_SEARCH", {}).get("MAX_ROWS", 10_000)
    if max_rows:
        if isinstance(current, list) and len(current) > max_rows:
            logger.warning(
                "Result set exceeds MAX_ROWS (%d). Truncating results.", max_rows
            )
            current = current[:max_rows]
        elif hasattr(current, "model") and hasattr(current, "values"):
            current = current[:max_rows]
        elif getattr(current.__class__, "__name__", "") in ("DataFrame", "Series"):
            current = current.head(max_rows)
    return current
