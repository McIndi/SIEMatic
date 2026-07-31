"""Generate the search command reference during an MkDocs build."""

import json
import os
from textwrap import dedent

import django
import mkdocs_gen_files


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SIEMatic.settings.web")
django.setup()

from search2.apps import generate_command_help_rows  # noqa: E402


def markdown_cell(value):
    """Format a value for use in a Markdown table cell."""
    if value is None:
        return "—"
    if isinstance(value, str):
        rendered = value
    else:
        rendered = json.dumps(value)
    return f"`{rendered}`" if rendered else "`\"\"`"


with mkdocs_gen_files.open("reference/search-commands.md", "w") as output:
    output.write(
        dedent(
            """\
            ---
            title: Search Commands
            ---

            # Search Commands

            This reference is generated from the search commands registered in
            `SIEMATIC_SEARCH["COMMANDS"]`. Each section documents one pipeline command.

            """
        )
    )
    for row in generate_command_help_rows():
        command = row["command"]
        description = (row["description"] or "No description provided.").strip()
        output.write(f"## `{command}`\n\n{description}\n\n")
        arguments = row["arguments"]
        if not arguments:
            output.write("This command accepts no arguments.\n\n")
            continue
        output.write("| Argument | Type | Default | Description |\n")
        output.write("| --- | --- | --- | --- |\n")
        for argument in arguments:
            help_text = " ".join(argument["help"].split()).replace("|", "\\|")
            output.write(
                f"| `{argument['flag']}` | `{argument['type']}` | "
                f"{markdown_cell(argument['default'])} | {help_text} |\n"
            )
        output.write("\n")
