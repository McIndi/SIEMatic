# SIEMatic Documentation Overhaul

## Context

Replace `README.md` + `plan_for_mvp.md` with a structured docs site published to
GitHub Pages at `mcindi.com/siematic/`. Admin + Deployment guides are merged into
one "Operations Guide" per prior decision.

## webutils Pages setup (reference point)

Cloned `mcindi/webutils` (`/workspace/webutils`) to check its Pages config:

- Single `main` branch, no `.github/workflows/*`, no `CNAME` file anywhere in the repo.
- `docs/` directory at repo root contains fully-built static HTML (`index.html`,
  `*.html`, `manifest-*.json`) plus a `.nojekyll` marker.
- All internal links are relative (`secret-share.html`, `manifest-index.json`);
  external links point to `https://www.mcindi.com` as a separate site.
- Direct `curl` to `mcindi.com` from this environment returns 403 (egress proxy
  blocks it) — could not confirm serving mechanism over HTTP.

Conclusion: webutils' `main:/docs` is very likely wired as the Pages source via
repo Settings → Pages ("Deploy from a branch"), no Action required. But nothing in
this repo maps `mcindi.com` → `mcindi.com/webutils/` — no CNAME, no custom-domain
config. That path-routing happens outside this repo (org-level Pages site, DNS,
or a reverse proxy the user manages elsewhere). **Open item**: confirm with the
user where that routing lives before wiring SIEMatic's publish step, or just
replicate the same pattern (`main:/docs`, static build committed, no custom domain
file in-repo) and let them slot it into the existing routing themselves.

## Outline

```
docs/
  index.md                              overview, architecture, licensing
  quickstart.md                         rundev walkthrough

  operations/                           merged admin + deployment guide
    index.md
    deploying.md                        compose, TLS/certs, env vars, bootstrap.py
    upgrading.md
    user-and-permission-management.md
    crawler-configuration.md
    findings-triage.md
    alerting.md
    data-retention.md
    scaling-and-performance.md
    backup-and-restore.md
    troubleshooting.md

  search-and-dashboards/
    index.md
    search-language.md
    saved-searches-and-sharing.md
    building-dashboards.md

  developer/
    index.md                            architecture/module map
    writing-a-search-command.md
    writing-a-crawler-plugin.md
    writing-an-agent-plugin.md
    testing-conventions.md
    contributing.md

  reference/
    index.md
    search-commands.md                  generated
    rest-api.md                         generated
    settings-and-env-vars.md            hand-written, CI-verified
    python-api.md                       generated (scoped modules)
    known-limitations.md

  history/
    plan_for_mvp.md                     archived
  changelog.md
```

`README.md` → short landing page + link to the published site.

## Actions

### Phase 0 — fact-check corrections (apply during migration, not before)
- Feature matrix: mark Cross-Database Joins done (`search2/commands/join.py`,
  registered in `SIEMATIC_SEARCH['COMMANDS']`); remove/soften SavedSearch
  "export/import" claim (not implemented — only whole-project `dumpdata`/`loaddata`).
- Fix `dashboards/` → `dashboarding/` in Project Structure.
- Standardize all compose commands on `docker compose` (drop `docker-compose` and
  `podman compose` variants) in Troubleshooting.
- Move any still-open item out of `plan_for_mvp.md` into
  `reference/known-limitations.md`; archive the file itself to `docs/history/`.
- Add a `reference/known-limitations.md` entry for the Dockerfile `HEALTHCHECK`
  bug (shared across all 4 compose services, only `siematic-web` listens on 8000)
  — no code fix here, doc note only.

### Phase 1 — toolchain
- `requirements-docs.txt`: mkdocs-material, mkdocstrings[python], mkdocs-gen-files,
  mkdocs-literate-nav.
- `requirements.txt` / `INSTALLED_APPS`: add drf-spectacular.
- `mkdocs.yml` at repo root: material theme, light/dark toggle, nav per outline
  above, `site_url` matching whatever base path webutils uses.
- Create `docs/` tree with stub pages (front-matter + one paragraph + TODO).
- CI: add `mkdocs build --strict` step.

### Phase 2 — reference generation
- Search command reference: `mkdocs-gen-files` script calls existing
  `search2.apps.generate_command_help_rows()` (do not reimplement argparse
  introspection) → one page per command in `reference/search-commands.md`.
- Consolidate the duplicate copy of that logic in
  `search2/components/command_help.py` to call the shared function.
- REST API reference: `manage.py spectacular --file docs/reference/openapi.yaml`
  as a build step, embed via Swagger UI/Redoc.
- `tools/docs/check_env_reference.py`: greps `os.getenv(` in
  `SIEMatic/settings/*.py`, diffs against `reference/settings-and-env-vars.md`,
  fails on drift.
- mkdocstrings scope: `crawlers.plugins.base`, `crawlers.models.Finding`,
  `agent.plugins.*`, `events.models`, `events.extractors` only. Do not point it at
  `search2.engine`/`search2.commands` (argparse-based, no real signatures to
  render) — those are covered by the generator above instead.

### Phase 3 — content migration
- Port README content into the new pages, applying Phase 0 corrections as each
  section moves. Slim README to a landing page once the site is live.

### Phase 4 — doc-example CI testing
- `tools/docs/test_doc_examples.py`: scan `docs/**/*.md` for tagged fences.
  - ` ```pipeline ` → run through `search2.engine.core.run_pipeline()` against a
    small fixture (reuse the `search2/tests.py` setUp pattern). Assert no exception.
  - ` ```console ` → run via subprocess with timeout, assert exit 0.
  - Untagged fences are not executed.
- Wire as a new step in the existing `test` job in `.github/workflows/ci.yml`.

### Phase 5 — publish
- New workflow: `mkdocs build --strict` → `actions/upload-pages-artifact` →
  `actions/deploy-pages`, on push to `main`.
- Confirm routing with the user (see open item above) before finalizing
  `site_url`/base path.

## Verification
- `mkdocs build --strict` passes.
- `manage.py check --settings SIEMatic.settings.web` and full test suite unchanged.
- `tools/docs/test_doc_examples.py` passes.
- `tools/docs/check_env_reference.py` passes.
- `reference/search-commands.md` lists every command in
  `SIEMATIC_SEARCH['COMMANDS']` with correct flags.
- `mkdocs serve` locally, confirm nav matches the outline.
- Visit the published site at the configured `site_url` to ensure all links and routing work as expected.
