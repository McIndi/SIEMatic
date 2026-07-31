---
title: Contributing
---

# Contributing

Create a focused branch from the current main branch, keep each change scoped,
and include tests and documentation for user-visible behavior. Do not commit
`.env`, generated private keys, databases, email output, or production event
data.

Before opening a pull request:

1. Install `requirements.txt` and `requirements-docs.txt` in a virtual environment.
2. Run Django checks and the complete test suite.
3. When API behavior changes, generate the OpenAPI schema.
4. Run the environment-reference checker and `mkdocs build --strict`.
5. When browser assets or templates change, run `collectstatic`.
6. Explain the user impact, security implications, and migration needs in the pull request.
7. Explain the manual checks that you completed.

Use Django includes and app static JavaScript for frontend work. Update vendored
dependencies with `tools/vendor_assets.py --update`. Make sure that the checksums
are correct. Then commit the updated manifest and assets together.

Preserve the role-specific settings split. Put shared defaults in
`SIEMatic/settings/base.py`. Put role-only behavior in `web.py`, `agent.py`,
`indexer.py`, or `crawler.py`. Give new extension points stable import paths and
clear configuration. Their failure messages must not disclose secrets.
