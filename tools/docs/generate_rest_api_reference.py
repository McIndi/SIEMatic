"""Generate the REST API reference during an MkDocs build.

Reuses drf-spectacular's own schema generator (the same one `manage.py
spectacular` calls) rather than reimplementing OpenAPI generation, then
renders the schema as plain Markdown instead of embedding an interactive
widget. SIEMatic is self-hosted with no fixed public API host, so a static
table-based reference avoids implying the docs domain is a live instance.
"""

import os
import sys
from pathlib import Path
from textwrap import dedent

import django
import mkdocs_gen_files


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SIEMatic.settings.web")
django.setup()

from drf_spectacular.settings import spectacular_settings  # noqa: E402

METHOD_ORDER = ["get", "post", "put", "patch", "delete"]


def get_schema() -> dict:
    """Build the OpenAPI schema in-process, exactly as `manage.py spectacular` does."""
    generator = spectacular_settings.DEFAULT_GENERATOR_CLASS(urlconf=None, api_version=None)
    return generator.get_schema(request=None, public=True)


def resolve(schema_or_ref: dict, components: dict) -> dict:
    """Follow a single `$ref` into `components.schemas`, if present."""
    if "$ref" in schema_or_ref:
        name = schema_or_ref["$ref"].rsplit("/", 1)[-1]
        return components.get("schemas", {}).get(name, {})
    return schema_or_ref


def type_label(prop: dict) -> str:
    """Render a short, human-readable type for one schema property."""
    if "$ref" in prop:
        return prop["$ref"].rsplit("/", 1)[-1]
    prop_type = prop.get("type", "any")
    if prop_type == "array":
        items = prop.get("items", {})
        return f"array of {type_label(items)}"
    if fmt := prop.get("format"):
        return f"{prop_type} ({fmt})"
    return prop_type


def properties_table(schema: dict, components: dict, direction: str) -> list[str]:
    """Render a schema's properties as a Markdown table.

    `direction` is "request" or "response": request tables drop readOnly
    fields (server-assigned, e.g. `id`), response tables drop writeOnly
    fields (input-only, e.g. a password) so each table reflects what a
    caller actually sends or receives.
    """
    schema = resolve(schema, components)
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    lines = []
    rows = []
    for name, prop in properties.items():
        if direction == "request" and prop.get("readOnly"):
            continue
        if direction == "response" and prop.get("writeOnly"):
            continue
        rows.append(
            (
                name,
                type_label(prop),
                "yes" if name in required else "no",
                (prop.get("description") or "").replace("\n", " ").strip() or "—",
            )
        )
    if not rows:
        return lines
    lines.append("| Field | Type | Required | Description |")
    lines.append("| --- | --- | --- | --- |")
    for name, type_str, required_str, description in rows:
        lines.append(f"| `{name}` | `{type_str}` | {required_str} | {description} |")
    lines.append("")
    return lines


def parameters_table(parameters: list[dict]) -> list[str]:
    """Render an operation's path/query parameters as a Markdown table."""
    if not parameters:
        return []
    lines = ["| Parameter | Location | Type | Required | Description |", "| --- | --- | --- | --- | --- |"]
    for param in parameters:
        schema = param.get("schema", {})
        lines.append(
            f"| `{param['name']}` | {param['in']} | `{type_label(schema)}` | "
            f"{'yes' if param.get('required') else 'no'} | "
            f"{(param.get('description') or '—').replace(chr(10), ' ')} |"
        )
    lines.append("")
    return lines


def security_line(operation: dict) -> str:
    schemes = {name for requirement in operation.get("security", []) for name in requirement}
    if not schemes:
        return "None"
    return ", ".join(sorted(schemes))


def render_operation(method: str, path: str, operation: dict, components: dict) -> list[str]:
    lines = [f"### `{method.upper()} {path}`", ""]
    if description := (operation.get("description") or "").strip():
        lines += [description, ""]
    lines += [f"**Authentication:** {security_line(operation)}", ""]

    lines += parameters_table(operation.get("parameters", []))

    request_body = operation.get("requestBody")
    if request_body:
        content = request_body.get("content", {})
        schema = next(iter(content.values()), {}).get("schema") if content else None
        if schema:
            lines.append("**Request body**")
            lines.append("")
            table = properties_table(schema, components, "request")
            lines += table if table else ["This request body has no documented fields.", ""]

    for status, response in operation.get("responses", {}).items():
        content = response.get("content", {})
        schema = next(iter(content.values()), {}).get("schema") if content else None
        lines.append(f"**Response `{status}`**")
        lines.append("")
        if not schema:
            lines += ["No response body.", ""]
            continue
        resolved = resolve(schema, components)
        if resolved.get("type") == "array":
            item_table = properties_table(resolved.get("items", {}), components, "response")
            lines.append("Array of:")
            lines.append("")
            lines += item_table if item_table else ["No documented fields.", ""]
        else:
            table = properties_table(schema, components, "response")
            lines += table if table else ["No documented fields.", ""]

    return lines


with mkdocs_gen_files.open("reference/rest-api.md", "w") as output:
    schema = get_schema()
    components = schema.get("components", {})
    info = schema.get("info", {})

    output.write(
        dedent(
            f"""\
            ---
            title: REST API
            ---

            # REST API

            {info.get('description', '')}

            This reference is generated from the OpenAPI schema that
            `python manage.py spectacular` produces. It documents the shape of
            each endpoint; it is not a live API console. SIEMatic is
            self-hosted, so replace `<your-siematic-host>` below with the
            base URL of your own deployment.

            The raw schema is available at [openapi.yaml](openapi.yaml).

            """
        )
    )

    paths = schema.get("paths", {})
    for path in sorted(paths):
        operations = paths[path]
        for method in METHOD_ORDER:
            if method not in operations:
                continue
            output.write("\n".join(render_operation(method, path, operations[method], components)))
            output.write("\n")
