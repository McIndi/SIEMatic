"""Execute tagged examples from the Markdown documentation.

Only ``pipeline`` and ``console`` fences are executable. All other fenced code
blocks are documentation and are deliberately ignored.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator


ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "docs"
FENCE = re.compile(r"^\s*```(?P<tag>[^\s`]*)\s*$")
EXECUTABLE_TAGS = {"pipeline", "console"}
CONSOLE_TIMEOUT_SECONDS = 30

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class Example:
    """A tagged Markdown code fence and its source location."""

    tag: str
    code: str
    path: Path
    line: int

    @property
    def location(self) -> str:
        return f"{self.path.relative_to(ROOT)}:{self.line}"


def iter_examples() -> Iterator[Example]:
    """Yield executable fenced examples from all documentation pages."""
    for path in sorted(DOCS_DIR.rglob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        index = 0
        while index < len(lines):
            match = FENCE.match(lines[index])
            if not match:
                index += 1
                continue

            tag = match.group("tag")
            opening_line = index + 1
            index += 1
            body: list[str] = []
            while index < len(lines) and not FENCE.match(lines[index]):
                body.append(lines[index])
                index += 1
            if index == len(lines):
                if tag in EXECUTABLE_TAGS:
                    raise ValueError(f"Unclosed code fence at {path.relative_to(ROOT)}:{opening_line}")
                break
            if tag in EXECUTABLE_TAGS:
                yield Example(tag, "\n".join(body).strip(), path, opening_line)
            index += 1


def configure_django(database_path: Path) -> None:
    """Configure Django to use an isolated SQLite database."""
    # Settings derive the log filename from argv; keep it a filename when this
    # tool is invoked through its repository-relative path.
    sys.argv[0] = Path(sys.argv[0]).name
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SIEMatic.settings.web")
    os.environ.setdefault("DJANGO_SECRET_KEY", "doc-example-tests-only-secret-key")
    os.environ["DATABASE_ENGINE"] = "django.db.backends.sqlite3"
    os.environ["DATABASE_NAME"] = str(database_path)
    for name in ("DATABASE_USER", "DATABASE_PASSWORD", "DATABASE_HOST", "DATABASE_PORT"):
        os.environ.pop(name, None)

    import django

    django.setup()

    from django.conf import settings

    # The join example intentionally demonstrates a second database alias. Both
    # aliases use the isolated fixture database so the example remains portable.
    settings.DATABASES["archive"] = {
        **settings.DATABASES["default"],
        "NAME": str(database_path),
    }


def create_fixture():
    """Create the small event and saved-search fixture used by pipeline examples."""
    from django.contrib.auth import get_user_model
    from django.core.management import call_command

    from events.models import Event
    from search2.models import SavedSearch

    call_command("migrate", verbosity=0, interactive=False)
    user = get_user_model().objects.create_superuser(
        username="doc-example-user",
        email="docs@example.invalid",
        password="doc-example-password",
    )
    for row in (
        {"host": "alpha", "index": "sysmon", "source": "fixture-a", "value": 1},
        {"host": "beta", "index": "sysmon", "source": "fixture-b", "value": 2},
        {"host": "alpha", "index": "application", "source": "fixture-c", "value": 3},
    ):
        Event.objects.create(
            host=row["host"],
            index=row["index"],
            source=row["source"],
            sourcetype="json",
            data=f'{{"value": {row["value"]}}}',
        )
    SavedSearch.objects.create(
        owner=user,
        name="Recent Sysmon Events",
        query="search --filter='index=\"sysmon\"' --order-by='[\"-created\"]' --limit=20",
    )
    return SimpleNamespace(user=user)


def run_pipeline_example(example: Example, request) -> None:
    """Run one documented pipeline and force lazy results to be evaluated."""
    from django.db.models import QuerySet

    from search2.engine.core import parse_pipeline, run_pipeline

    fixture_rows = [
        {"host": "beta", "value": 2, "tags": {"kind": "server"}},
        {"host": "alpha", "value": 1, "tags": {"kind": "client"}},
        {"host": "alpha", "value": 3, "tags": {"kind": "client"}},
    ]
    stages = parse_pipeline(example.code)
    initial_data = None if stages and stages[0].cmd in {"search", "run_saved_search"} else fixture_rows
    result = run_pipeline(
        initial_data,
        example.code,
        request=request,
        environ={"row_count": 20},
    )
    if isinstance(result, QuerySet):
        list(result)


def run_console_example(example: Example, database_path: Path) -> None:
    """Run one documented console block in a subprocess."""
    environment = os.environ.copy()
    environment["DATABASE_ENGINE"] = "django.db.backends.sqlite3"
    environment["DATABASE_NAME"] = str(database_path)
    subprocess.run(
        example.code,
        cwd=ROOT,
        env=environment,
        shell=True,
        check=True,
        timeout=CONSOLE_TIMEOUT_SECONDS,
    )


def main() -> int:
    examples = list(iter_examples())
    if not examples:
        print("No tagged documentation examples found.")
        return 0

    failures: list[tuple[Example, Exception]] = []
    with tempfile.TemporaryDirectory(prefix="siematic-doc-examples-") as temp_dir:
        database_path = Path(temp_dir) / "db.sqlite3"
        configure_django(database_path)
        request = create_fixture()

        for example in examples:
            try:
                if not example.code:
                    raise ValueError("Executable code fence is empty")
                if example.tag == "pipeline":
                    run_pipeline_example(example, request)
                else:
                    run_console_example(example, database_path)
            except Exception as exc:  # Report all examples before failing CI.
                failures.append((example, exc))
                print(f"FAIL {example.location} ({example.tag}): {exc}", file=sys.stderr)
            else:
                print(f"PASS {example.location} ({example.tag})")

        from django.db import connections

        connections.close_all()

    if failures:
        print(f"{len(failures)} of {len(examples)} documentation examples failed.", file=sys.stderr)
        return 1
    print(f"All {len(examples)} tagged documentation examples passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
