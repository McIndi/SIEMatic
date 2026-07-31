"""Fail when Django settings and the environment-variable reference drift."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SETTINGS_DIR = ROOT / "SIEMatic" / "settings"
REFERENCE = ROOT / "docs" / "reference" / "settings-and-env-vars.md"
DOCUMENTED_ROW = re.compile(r"^\|\s*`([A-Z][A-Z0-9_]*)`\s*\|", re.MULTILINE)
ENV_HELPERS = {"env_bool", "env_list"}


def configured_variables() -> set[str]:
    """Return literal environment names read by settings modules."""
    variables: set[str] = set()
    for path in SETTINGS_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            function = node.func
            is_getenv = (
                isinstance(function, ast.Attribute)
                and function.attr == "getenv"
                and isinstance(function.value, ast.Name)
                and function.value.id == "os"
            )
            is_helper = isinstance(function, ast.Name) and function.id in ENV_HELPERS
            first_arg = node.args[0]
            if (is_getenv or is_helper) and isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                variables.add(first_arg.value)
    return variables


def documented_variables() -> set[str]:
    return set(DOCUMENTED_ROW.findall(REFERENCE.read_text(encoding="utf-8")))


def main() -> int:
    configured = configured_variables()
    documented = documented_variables()
    missing = sorted(configured - documented)
    stale = sorted(documented - configured)
    if not missing and not stale:
        print(f"Environment reference is current ({len(configured)} variables).")
        return 0
    if missing:
        print("Missing from reference:", ", ".join(missing), file=sys.stderr)
    if stale:
        print("Documented but not read by settings:", ", ".join(stale), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
