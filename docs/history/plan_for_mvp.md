---
title: Path to MVP (Archived)
---

# SIEMatic — Path to MVP

!!! note "Historical document"
    This completed implementation plan is retained for project history. It is
    not the current roadmap. Outstanding constraints are tracked in
    [Known Limitations](../reference/known-limitations.md).

## Context

SIEMatic is an unreleased Django-based SIEM (event collection → indexing → search → detection → alerting). The architecture is sound and the search DSL works, but the project cannot currently be run by anyone who clones it, and its access-control model gives any self-registered user read access to every security log.

Verified against the current tree (fresh venv, Django 6.0.7):

- `django.setup()` raises `ValueError: Unable to configure handler 'file'` — the logging `FileHandler` targets a gitignored `logs/` dir that doesn't exist. This also breaks `docker build` (collectstatic runs in the builder).
- `check --deploy` → 5 security warnings; `SECRET_KEY` falls back to a hardcoded literal without complaint; `DEBUG` is hardcoded `False` with the env-driven line commented out.
- 23 tests pass, but they cover field-name extraction and SavedSearch CRUD only — nothing tests the search engine, authz, ingest, or crawlers.
- The new-user permission signal grants `project.view_savedsearch` instead of `search2.view_savedsearch` (confirmed) because duplicate permission codenames exist and the signal filters on codename alone.
- Any user can execute another user's saved search by name (confirmed end-to-end).

Goal: a SIEMatic that a stranger can clone, start, and trust — running over TLS, with admin-provisioned accounts, correct permissions, a findings triage UI, and a test suite that actually guards the behavior.

**Decisions taken:** app-native TLS (no reverse proxy); DB-backed alert subscriptions deferred to post-MVP; Findings get list/detail + triage state; a `rundev` all-in-one command replaces the sample-data script; Python dependencies stay unpinned deliberately (CI acts as the latest-deps canary).

---

## Phase 0 — Make it run, and keep it running

No behavior change. Everything downstream depends on this.

**Files:** `.gitignore`, `logs/.empty`, `LICENSE`, `.dockerignore`, `Dockerfile`, `.github/workflows/ci.yml`, `SIEMatic/settings/base.py`, `indexer/management/commands/indexer.py`

1. **`logs/` in the repo.** Remove the `logs/` line from `.gitignore`, add `logs/.empty`, and add `*.log` (already present) so only the directory is tracked. Belt-and-braces: have `base.py` `mkdir(parents=True, exist_ok=True)` the log dir before the `LOGGING` dict is evaluated — the container and CI both need this to be unconditional.
2. **`.gitignore` currently ignores `.github/`** — remove that line or the CI workflow can never be committed. Also drop `.claude/`? (leave as-is, intentional.)
3. **Dockerfile:** `mkdir -p /app/log` → `/app/logs`. Add a `HEALTHCHECK`.
4. **`.dockerignore`:** exclude `.env`, `*.sqlite3`, `venv/`, `.venv/`, `logs/*.log`, `staticfiles/`, `build/`, `dist/`, `.git/`, `__pycache__/`. Today `COPY . .` bakes local secrets into image layers.
5. **`LICENSE`:** add the BSL text at the repo root, with the parameters filled in (Licensor: McIndi; Change Date; Change License; Additional Use Grant covering individuals, non-profit, and educational use, matching the README). Add the standard BSL header note to the README license section pointing at the file.
6. **CI** — `.github/workflows/ci.yml`, on push/PR:
   - matrix: ubuntu-latest × Python 3.13, 3.14
   - `pip install -r requirements.txt` (unpinned on purpose — this job is the early-warning system for upstream breakage)
   - `manage.py check --settings SIEMatic.settings.web`
   - `manage.py test --settings SIEMatic.settings.web`
   - `docker build .` as a separate job
   - `DJANGO_SECRET_KEY` supplied via workflow `env` (required after Phase 1)
7. **Delete the dead channel layer** (see briefing below): remove `CHANNEL_LAYERS` from `base.py` and the unused `from channels.layers import get_channel_layer` at `indexer/management/commands/indexer.py:12`.

### Briefing: InMemoryChannelLayer alternatives (item 17)

**Nothing in SIEMatic uses the channel layer.** `EventConsumer` (`indexer/consumers.py`) never calls `group_add` or `group_send` — it receives frames and writes to the DB. The only reference in the codebase is an unused import. The layer is configured but inert, so the "doesn't work across processes" concern is currently theoretical.

Options for when you *do* need fan-out (live tail, pushing new findings to open browsers):

| Option | Verdict |
|---|---|
| **`channels-redis` (`RedisChannelLayer`)** | The only production-grade choice. Officially maintained by the Channels project, supports sharding and sentinel. Cost: a Redis container. **Recommended when fan-out is needed.** |
| **`channels-postgres`** | Community-maintained, reuses the Postgres you already run — attractive for air-gapped single-node installs. Smaller community; verify maintenance before depending on it. |
| **`InMemoryChannelLayer`** | Single-process only. Fine for tests; silently drops cross-process messages in production. |
| **No layer (today)** | Correct for MVP. Delete the config so it isn't mistaken for a working guarantee. |

**Action: remove it now.** Reintroduce `channels-redis` in the same PR as the first feature that needs it.

---

## Phase 1 — Settings driven by environment

**Files:** `SIEMatic/settings/base.py`, `SIEMatic/settings/web.py`, `.env.example`, `docker-compose.yaml`

1. Add small helpers at the top of `base.py`: `env_bool(name, default)`, `env_list(name, default)`. Use them consistently — `ALLOWED_HOSTS` already hand-rolls a `.split(',')`.
2. `DEBUG = env_bool('DJANGO_DEBUG', False)` — restore the commented-out line. Guard the `debug_toolbar` block with an import check (`importlib.util.find_spec`), because `debug_toolbar` is **not** in `requirements.txt`; today setting `DEBUG=True` crashes on `INSTALLED_APPS`.
3. **`SECRET_KEY` fails fast:** raise `ImproperlyConfigured` when `DJANGO_SECRET_KEY` is unset or equals the placeholder. Remove the hardcoded literal entirely. Document generating one (`python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`) in `.env.example` and the README.
4. **TLS-gated security settings** (item 9) — one switch, `SIEMATIC_TLS_ENABLED` (default `False`):
   ```python
   TLS_ENABLED = env_bool('SIEMATIC_TLS_ENABLED', False)
   SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = TLS_ENABLED
   SECURE_SSL_REDIRECT   = TLS_ENABLED
   SECURE_HSTS_SECONDS   = 31536000 if TLS_ENABLED else 0
   SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_PRELOAD = TLS_ENABLED
   ```
   Keeping plain-HTTP local dev working while making `check --deploy` clean whenever TLS is on.
5. **SMTP email** (the MVP slice of item 18): drive `EMAIL_BACKEND`/`EMAIL_HOST`/`EMAIL_PORT`/`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`/`EMAIL_USE_TLS`/`DEFAULT_FROM_EMAIL` from env, defaulting to the filebased backend. Today `crawler.py` hardcodes filebased, so alerting silently never sends. Alert *recipients* stay in `ALERTING_CONFIGS` for MVP.
6. Extend `.env.example` and the compose `environment:` blocks with every new variable.

The database-backed alert-subscription work deferred by this plan remains
outstanding and is now tracked in
[Known Limitations](../reference/known-limitations.md).

---

## Phase 2 — Authentication and authorization

The security core. Best reviewed as one PR.

**Files:** `project/{models,signals,urls,views,forms}.py`, `project/templates/{base,login,register}.html`, `project/templates/registration/login.html`, new `project/migrations/000X_*`, `search2/{models,views,api}.py`, `search2/commands/run_saved_search.py`, `dashboarding/views.py`, `events/views.py`, `SIEMatic/settings/base.py`

1. **Remove self-registration (item 2).**
   - Drop the `register/` path from `project/urls.py`, the `register` view from `project/views.py`, and `project/templates/register.html`.
   - Remove the "Register" nav item (`project/templates/base.html:199`) and the "Register for an account" links in both `login.html` and `registration/login.html`.
   - **Keep `CustomUserCreationForm`** — it's `CustomUserAdmin.add_form` and is what makes admin-created users get properly hashed passwords.
   - Update `project/tests.py::UserRegistrationTests` → assert `reverse('register')` raises `NoReverseMatch` and `/register/` returns 404.

2. **Fix the permission model (item 6).**
   - Delete the `Meta.permissions` block from `CustomUser` (`project/models.py:14`) and generate the accompanying `AlterModelOptions` migration (mirrors the existing `0004_alter_customuser_options.py`).
   - Rewrite `project/signals.py` to resolve permissions by **content type**, not bare codename:
     ```python
     DEFAULT_PERMISSIONS = [
         ('events', 'event', 'view_event'),
         ('dashboarding', 'dashboard', 'view_dashboard'),
         ('dashboarding', 'panel', 'view_panel'),
         ('crawlers', 'finding', 'view_finding'),
         ('search2', 'savedsearch', 'view_savedsearch'),
     ]
     ```
     Look each up via `ContentType.objects.get_for_model()` / `get_by_natural_key`, and log an error if one is missing rather than silently skipping.
   - Add a **data migration** that deletes the orphaned `project.view_*` Permission rows and rebuilds the `Registered User` group from `DEFAULT_PERMISSIONS`, so existing dev databases self-heal.
   - Move group setup out of the per-user `post_save` — the group's permissions never change per user. Use a `post_migrate` receiver for group/permission setup; keep `post_save` only for adding the user to the group.

3. **Saved-search visibility (item 7).**
   - Add to `SavedSearch`: `shared_with = M2M(AUTH_USER_MODEL, blank=True, related_name='shared_searches')` and `is_public = BooleanField(default=False)`.
   - Add one reusable manager method — **this is the single chokepoint, use it everywhere**:
     ```python
     class SavedSearchQuerySet(models.QuerySet):
         def visible_to(self, user):
             return self.filter(Q(owner=user) | Q(shared_with=user) | Q(is_public=True)).distinct()
     ```
   - Apply it in all four call sites: `run_saved_search._run` (currently an unscoped `SavedSearch.objects.get(name=...)` — the confirmed cross-user leak), `search2/views.py::savedsearch_list`, the `saved_searches` context in `search2/views.py::dashboard`, and `SavedSearchViewSet.get_queryset`.
   - **Edit and delete stay owner-only** — the existing `get_object_or_404(..., owner=request.user)` calls are correct; leave them.
   - Names are no longer unique per user for lookup purposes: resolve `run_saved_search <name>` as owner-first, then shared, and raise a clear error on ambiguity.

4. **`@login_required` on `panel_preview`** (`dashboarding/views.py:118`) — the only unauthenticated route into the search pipeline.

5. **DRF permissions and throttling (item 12).**
   - `DEFAULT_PERMISSION_CLASSES = ['rest_framework.permissions.IsAuthenticated']` — currently unset, so it defaults to `AllowAny` for any view that forgets to declare.
   - `EventViewSet` → `DjangoModelPermissions` so writes require `events.add_event`. Ordinary users have view-only; create an **`Agent`** group holding `add_event`, and document putting the agent's service account in it. This closes log forgery by any logged-in user.
   - Throttling — scoped, since ingest and search have wildly different profiles:
     ```python
     'DEFAULT_THROTTLE_CLASSES': ['rest_framework.throttling.ScopedRateThrottle'],
     'DEFAULT_THROTTLE_RATES': {'ingest': '20000/hour', 'search': '120/min', 'anon': '20/hour'},
     ```
     `throttle_scope = 'ingest'` on `EventViewSet`, `'search'` on `Search2RunView`. Make the rates env-overridable — ingest volume is deployment-specific.
   - Note: `BasicAuthentication` stays in `DEFAULT_AUTHENTICATION_CLASSES`; it becomes defensible once Phase 3 lands.

---

## Phase 3 — App-native TLS

**Files:** `project/management/commands/serve.py`, `indexer/management/commands/indexer.py`, `agent/plugins/plugin_process_manager.py`, `SIEMatic/settings/{base,agent,indexer}.py`, `docker-compose.yaml`, `.env.example`, new `tools/gen_dev_cert.py`

1. **Web server** — `serve.py` already has `--ssl/--ssl-cert/--ssl-key` backed by `CHERRYPY_SSL*` env vars. Verify it end-to-end and switch `server.ssl_module` from `'builtin'` to `'builtin'` only after confirming; document cert/key paths in `.env.example`.
2. **Indexer** — the Daphne subprocess (`indexer.py`) has no TLS. Daphne takes `-e ssl:<port>:privateKey=<key>:certKey=<cert>` endpoint syntax; build the endpoint string from `INDEXER_SSL_CERT`/`INDEXER_SSL_KEY` env vars, falling back to plain `-b/-p` when unset.
3. **Agent** — `plugin_process_manager.py` hardcodes `http://` (line 57) and `ws://` (line 116). Derive the scheme from an `INDEXER_TLS` setting; add `INDEXER_CA_BUNDLE` for self-signed trust, passed to both `requests` (`verify=`) and `websockets.connect` (`ssl=`). Never default to disabling verification.
4. **Dev certs** — `tools/gen_dev_cert.py` generates a self-signed cert+key into `certs/` (gitignored) so `SIEMATIC_TLS_ENABLED=1` works on a fresh clone. Wire it into `rundev` (Phase 7).
5. **Compose** — mount `certs/`, set `SIEMATIC_TLS_ENABLED=True` and the cert paths for `siematic-web` and `siematic-indexer`.
6. Correct the README feature matrix: "Agent Framework — WebSocket (TLS)" becomes true only after this phase; it is currently a false claim.

**Verification gate:** `manage.py check --deploy` must report **zero** issues with `SIEMATIC_TLS_ENABLED=1`.

---

## Phase 4 — Ingest correctness: extract once, write once

**Files:** `events/{models,signals,serializers,extractors}.py`, `events/views.py`, `indexer/consumers.py`, `SIEMatic/settings/agent.py`, `agent/plugins/watchdog_plugin.py`

1. **The current double-write (item 19).** `events/signals.py` runs extraction in `post_save` and calls `event.save()` again — two writes per event on the hot path. Worse, `BulkEventSerializer.create()` uses `bulk_create`, which fires no `post_save` at all, so **bulk-ingested events are never extracted** — and bulk is the path the agent actually uses.
2. **Fix:** add `apply_extractions(event) -> Event` to `events/extractors.py` — mutates `extracted_fields` in memory, performs no DB write, reuses the existing `settings.FIELD_EXTRACTIONS` predicate/extractor pairs and the existing per-extractor `try/except` logging.
   - Call it from an overridden `Event.save()` (guarded so it runs pre-insert) → one write for the single-event path.
   - Call it over the instance list in `BulkEventSerializer.create()` before `bulk_create` → bulk events get extraction, still one write.
   - **Delete the `post_save` receiver** and the `_extraction_done` recursion flag it needed.
3. **Batch the WebSocket path.** `indexer/consumers.py::create_events` loops `_create_single_event` one row at a time — a 500-event agent batch becomes 500 round trips. Split into "build instances" and "persist", then `bulk_create` the list case. Keep the per-item JSON-parse error handling; a single malformed event must not drop the batch.
4. **Watchdog default (item 13).** `WatchdogPlugin` reads `config.get('path_to_watch', '.')` but `settings/agent.py` never sets `path_to_watch` — so it recursively watches the **entire project directory**, including the `logs/` dir the agent itself writes to. Feedback loop.
   - Set `enabled: False` by default and add an explicit `path_to_watch` to the config.
   - Add a guard in `WatchdogPlugin.__init__` that refuses (and logs an error) if the resolved watch path contains `settings.BASE_DIR / 'logs'`.

---

## Phase 5 — Findings triage UI

Findings are the product's actual output and are currently visible only in Django admin, which non-staff users can't reach.

**Files:** new `crawlers/{urls,forms}.py` + `crawlers/templates/crawlers/*.html`, `crawlers/{models,views,admin}.py`, `SIEMatic/urls.py`, `project/templates/base.html`, new `crawlers/migrations/000X_*`

1. **Model** — add to `Finding`: `status` (`new`/`acknowledged`/`in_progress`/`resolved`/`false_positive`, default `new`, `db_index=True`), `assignee` (FK to user, null), `notes` (TextField, blank). Migration included. Add `Meta.permissions` — no: use the auto-generated `change_finding` for triage actions and keep `delete_finding` staff-only.
2. **Views** (mirror the `dashboarding` CRUD shape — `dashboarding/views.py` + its templates are the house pattern):
   - `finding_list` — filterable by severity, status, rule_name, date range; DataTables-backed like `dashboard_list.html`.
   - `finding_detail` — full description, MITRE tactic/technique, the linked `Event` and its `extracted_fields`, triage form.
   - `finding_update` — status/assignee/notes only; requires `crawlers.change_finding`.
   - `finding_delete` — staff only, mirroring `dashboard_confirm_delete.html`.
   - Bulk status update from the list page.
   - All `@login_required` + `@permission_required('crawlers.view_finding')`.
3. **Templates** extend `base.html` and reuse the existing Bootstrap table/card idiom. After Phase 6 they use vendored assets, not CDN links.
4. Register `crawlers.urls` under `/findings/` in `SIEMatic/urls.py` (non-indexer branch only) and add a nav link in `base.html`.
5. Extend `FindingAdmin` with the new fields in `list_display`/`list_filter`.

---

## Phase 6 — Vendor the frontend

Every template pulls Bootstrap, jQuery, Chart.js, DataTables, jsZip and pdfmake from CDNs — incompatible with the air-gapped deployment story the README already advertises. Two conflicting DataTables versions (1.13.7 and 2.3.4) are loaded across different templates, and `chart.js` is fetched from an **unpinned** URL with no SRI.

**Files:** new `tools/vendor_assets.py` + `tools/vendor_manifest.json`, `static/vendor/**`, all templates under `project/`, `search2/`, `dashboarding/`

1. **`tools/vendor_assets.py`** — downloads each asset to `static/vendor/<pkg>/<file>`, verifies against a recorded SHA-256, and rewrites the manifest with `--update` to pull the current latest (this is item 16's "pull the latest of all into the repo", the frontend counterpart to leaving Python deps unpinned).
   - **Reuse `bootstrap.py`'s existing helpers** — `get_file_sha256()` and its `requests`-based download logic already do exactly this. Either import them or add `vendor_assets` as a new `bootstrap.py` subcommand alongside `download_python`/`run_pip_install`, which is the more consistent home.
2. Standardize on **one** DataTables major version (2.x) across all templates; the mixed 1.13.7/2.3.4 loading is a live bug.
3. Replace every CDN `<link>`/`<script>` with `{% static 'vendor/...' %}`. Commit the vendored files so a clone is self-sufficient.
4. Confirm `collectstatic` + WhiteNoise's `CompressedManifestStaticFilesStorage` handle them (note: `STATICFILES_STORAGE` is the pre-4.2 spelling — migrate to `STORAGES['staticfiles']` while here, since CI runs Django 6).

---

## Phase 7 — Developer experience

**Files:** new `project/management/commands/rundev.py`, delete `create_sample_data.py`, `README.md`

1. **`manage.py rundev`** — starts the web server, the indexer, and an agent (sysmon plugin only) as a supervised process tree against SQLite, generating a dev cert via `tools/gen_dev_cert.py` if missing. A fresh clone shows **real host telemetry** within seconds of the first command. Reuse the subprocess-supervision pattern already in `indexer.py` and `PluginProcessManager` rather than inventing a third.
2. **Delete `create_sample_data.py`** — it references `SIEMatic.settings.dev`, which does not exist; the script is already dead code.
3. **README** — rewrite Getting Started around `rundev`; document admin user creation now that self-registration is gone; document every new env var; fix the feature-matrix rows this plan makes true (TLS, notifications) and the ones it doesn't. Leave `CHANGELOG.md` empty until first release.

---

## Phase 8 — Test suite

Write tests **within each phase**; this phase closes the remaining gaps and sets the coverage floor.

**Files:** `*/tests.py` (convert to `tests/` packages where a module gets large)

| Area | Coverage |
|---|---|
| `events` | Extraction on single **and** bulk paths; `assertNumQueries` proving exactly one write per event; malformed-JSON handling |
| `indexer` | `WebsocketCommunicator` accept-when-authenticated / reject-when-anonymous; batch ingest persists N events in one query. **Rewrite the commented-out block in `events/tests.py`** — it currently calls the agent's real `get_session_cookie` against a live server, which is why it was disabled |
| `search2` | Each pipeline command; authz denial for `project.CustomUser` and `search2.SavedSearch`; the saved-search visibility matrix (owner / shared / public / stranger); `MAX_ROWS` truncation |
| `project` | Signal grants the correct **content-typed** permissions (this is the regression that exists today); `/register/` is 404 |
| `crawlers` | Finding creation + `realert_cooldown`; retention crawler deletes only matching rows; `EmailAlert` sends via `locmem`; findings views permission matrix |
| `dashboarding` | `panel_preview` requires login; panel param substitution |
| API | Throttle returns 429 past the limit; a view-only user gets 403 on event create |

Housekeeping: `search2/tests.py` contains non-test helpers (`debug_timestamp_fields`, `debug_chart_data_processing`) — and `debug_chart_data_processing` imports from `search2.static.search2.chart`, a **JavaScript file**, so it would raise if ever called. Move real helpers to `search2/utils.py`; delete the broken one.

Add `--settings SIEMatic.settings.web` consistently and wire coverage reporting into the Phase 0 CI job.

---

## Verification

Per phase, and again at the end:

```bash
python manage.py check --settings SIEMatic.settings.web
```

```bash
SIEMATIC_TLS_ENABLED=1 python manage.py check --deploy --settings SIEMatic.settings.web
```

```bash
python manage.py test --settings SIEMatic.settings.web
```

End-to-end, from a **clean clone in a fresh venv** (the current tree fails at step one):

1. `pip install -r requirements.txt` → `python manage.py rundev` starts without touching `.env`, generates a dev cert, and serves over HTTPS.
2. Within ~30s, `search --limit=10` on the search dashboard returns real sysmon events from the host — proving agent → indexer → DB → search.
3. `curl -k https://localhost:8000/register/` → **404**.
4. Create a user in Django admin; confirm they hold exactly `events.view_event`, `dashboarding.view_dashboard`, `dashboarding.view_panel`, `crawlers.view_finding`, `search2.view_savedsearch` — note `search2.`, not `project.`.
5. As that user, `POST /api/events/` → **403** (no `add_event`). Add them to the `Agent` group → 201.
6. Hammer `/search2/api/run/` past the throttle → **429**.
7. User A creates a saved search; user B running `run_saved_search <name>` gets an error until A shares it.
8. `docker build . && docker compose up` → all five services healthy; `.dockerignore` keeps `.env` out of the image (`docker history` / `docker run --rm <img> ls -a` shows no `.env`).
9. Trigger a finding (`manage.py run_crawlers --plugin always_finding_crawler`); it appears at `/findings/`, can be acknowledged, and an email lands in the configured backend.
10. With the network disabled, load every page — no external asset requests (check the browser network tab).
```
