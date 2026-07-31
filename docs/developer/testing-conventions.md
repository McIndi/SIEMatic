---
title: Testing Conventions
---

# Testing Conventions

Tests live in each Django app's `tests.py` and run with the web settings. Use
Django `TestCase` for database and request behavior and plain unit-style test
methods for isolated parsers or helpers. Build the smallest fixtures needed.
When you exercise protected views or pipelines, authenticate requests explicitly.

Run the checks used by CI:

```bash
python manage.py check --settings SIEMatic.settings.web
python manage.py test --settings SIEMatic.settings.web
python tools/docs/check_env_reference.py
mkdocs build --strict
```

CI runs the Django suite on Python 3.13 and 3.14 and collects coverage. It checks
a TLS-enabled deployment configuration. It also builds static assets, the Docker
image, the OpenAPI schema, and this site. CI checks the environment-variable
documentation for accuracy.

Write regression tests that fail before the fix and exercise observable behavior.
Search commands need coverage for each supported input kind and permissions.
Use controlled fakes for network access, clocks, sleep, multiprocessing, and
email delivery in agent and crawler tests. Keep tests independent of execution
order and external services.

When a setting reads a new environment variable, update
`docs/reference/settings-and-env-vars.md`. When a REST serializer or view
changes, regenerate `docs/reference/openapi.yaml`. Command argparse changes are
picked up automatically by the docs generator.
