# SIEMatic

SIEMatic is a fair-sourced observability platform built with Django, designed for modern event collection, indexing, and search. It provides a modular architecture for ingesting, processing, and querying event data, with a focus on extensibility, security, and developer productivity.

## Overview

- **Event Collection:** Pluggable agent system for collecting events from files, directories, and other sources.
- **Indexing:** Asynchronous indexer for storing and managing event data.
- **Search:** Powerful, settings-driven search language supporting QuerySet pipelines, filtering, grouping, and annotation while enforcing permissions.
- **Crawlers:** Plugin-based analytics for continuous monitoring, alerting, and automated data retention with findings and MITRE ATT&CK integration. Supports multiple concurrent instances with flexible scheduling.
- **User Management:** Custom user model and profile with theme preferences.
- **REST API:** Extensible endpoints for event ingestion and querying.
- **Modern UI:** Responsive templates with Bootstrap, user authentication, and profile management.

# 🧩 SIEMatic Feature Matrix & Roadmap

## **Feature Matrix**

| Category                       | Feature                        | Status                    | Implementation Layer       | Notes                                                                        |
| ------------------------------ | ------------------------------ | ------------------------- | -------------------------- | ---------------------------------------------------------------------------- |
| **Core Search & Querying**     | Search Language Core           | ✅ Implemented             | Python (pipeline parser)   | Custom shlex/argparse-based DSL tied to Django ORM, Pandas, and Records      |
|                                | Search Command Implementations | 🟡 In Progress            | Python registry            | Base commands (`search`, `aggregate`, `annotate`) working; expansion planned |
|                                | SavedSearch System             | ✅ Implemented             | Django model               | Versionable, reusable queries with export/import                               |
|                                | SavedSearch Params / Args      | 🔴 Not Started            | Django / Parser            | Needs support for variables and templating                                   |
| **Data Model & Indexing**      | Event Indexer                  | ✅ Implemented             | Django ORM                 | Uses Django models for events; leverages BRIN where possible                 |
|                                | BRIN Index Recommendation      | ✅ Documented              | Postgres setup guide       | Users create index manually when provisioning                                |
|                                | Cross-Database Joins           | 🟡 Planned                | Pandas join layer          | To be implemented next; enables multi-source analysis                        |
|                                | Multi-Database Design          | ✅ Implemented             | Django settings / Pandas   | Configurable, multi-source querying through ORM + Pandas                     |
| **Dashboards & Visualization** | Dashboard Builder              | ✅ Implemented             | django-components          | Handles populating searches + dynamic panels                                 |
|                                | Panel System                   | ✅ Implemented             | Django models/components   | Panels represent chart/table visualizations                                  |
|                                | Template Tags                  | 🔴 Dropped                | Replaced by Components     | Former Chart/Table tags deprecated                                           |
| **Agents & Indexers**          | Agent Framework                | ✅ Implemented             | WebSocket (TLS)            | Authenticated communication between agent/indexer                            |
|                                | WorkerNode Tracking            | 🔴 Not Implemented        | Django model               | To track UUID, hostname, first_seen, last_seen                               |
| **Crawlers / Analytics**       | Crawler Framework              | ✅ Implemented             | Django + Multiprocessing   | Plugin-based daemon/scheduled analytics with restart & cooldown; supports continuous and cron-based runs; multiple instances per plugin |
|                                | MITRE ATT&CK Integration       | ✅ Implemented             | Django model / JSON import | Maps findings to tactics/techniques in plugins and models; dataset import planned |
|                                | Findings / Alerts              | ✅ Implemented             | Django model               | Generates alerts with configurable re-alert cooldown and severity levels |
|                                | Notification Hooks             | ✅ Implemented             | Email backend              | Email alerting for findings; extensible plugin system for other hooks |
|                                | Data Retention                 | ✅ Implemented             | Scheduled crawler          | Automated deletion of old events with configurable retention periods and field-based filtering |
| **Security & Access**          | Auth & RBAC                    | ✅ Implemented             | Django auth                | Native Django users/groups/permissions                                       |
|                                | Django Guardian Integration    | 🔴 Not Implemented        | Optional plugin            | Will allow row-level object permissions                                      |
|                                | API Authentication             | ✅ Implemented             | DRF token/session          | Uses Django REST framework                                                   |
| **System Design**              | Async / Concurrent Execution   | ✅ Implemented selectively | asyncio / Django-Q ready   | Applied where beneficial (searches, agent comms)                             |
|                                | Plugin/Extension System        | ✅ Implemented             | Registry                   | Search commands and agents register dynamically                              |
|                                | REST API                       | ✅ Implemented             | Django REST framework      | Provides CRUD for dashboards, searches, events                               |
|                                | Data Import / Export           | ✅ Implemented             | `dumpdata` / `loaddata`    | Full project export (events, dashboards, users, etc.)                        |
|                                | Admin Dashboard                | ✅ Implemented             | Django admin               | Consolidated view of key models                                              |
|                                | Logging & Metrics              | 🟡 Partial                | Python logging             | Structured event logging active, metrics planned                             |
| **Licensing / Productization** | Licensing Model                | ✅ Defined                 | BSL-like policy            | Free for personal, non-profit, edu; paid for commercial                      |
|                                | Docs & Example Datasets        | 🔴 Not Started            | Markdown / Fixtures        | Required for MVP release                                                     |

---

## 🛠 **Roadmap**

### **Phase 1 — MVP Completion (Now → Next Milestone)**

Goal: Deliver self-contained, end-to-end SIEMatic that can ingest, search, visualize, and analyze.

1. ✅ Finalize **search command library**
2. ✅ Implement **crawler system**
   - ✅ Continuous + scheduled runs (daemon and cron-based)
   - ✅ Findings + MITRE mapping (with tactics/techniques in findings)
   - ✅ Data retention policies (configurable per instance)
3. 🔴 Implement **SavedSearch params/args**
4. 🔴 Add **WorkerNode tracking model**
5. 🟡 Enable **cross-database joins** via Pandas
6. 🟡 Extend **SavedSearch export/import** to include crawlers and findings
7. 🟡 Add **basic metrics + structured logging**
8. 🔴 Draft **example datasets** and quickstart docs

---

### **Phase 2 — Enrichment & Hardening**

Goal: Improve analysis depth, reliability, and extensibility.

1. 🟡 Add **MITRE ATT&CK dataset** import + mapping UI (basic mapping implemented in findings)
2. ✅ Add **Notifications** (email alerting implemented)
3. 🔴 Optional **Django Guardian integration**
4. 🟡 Refine **RBAC enforcement** at search-command layer
5. 🟡 Implement **dashboard export/import versioning**
6. 🟡 Implement **crawler scheduling and management command** (run_crawlers command implemented)
7. 🔴 Start **unit tests + coverage suite**

---

### **Phase 3 — Productization & Documentation**

Goal: Prep for public and commercial adoption.

1. 🟡 Add **user guide** (install, configure, extend)
2. 🟡 Add **developer guide** (build plugins, commands)
3. 🟡 Finalize **BSL-style license text**
4. 🟡 Package **docker-compose deployment**
5. 🟡 Publish **example dashboards + search packs**
6. 🔴 Optional **multi-tenant enhancements**


## Getting Started

### Prerequisites

- Python 3.10+
- pip
- virtualenv
- Git

### Setup Instructions

1. **Clone your project**
   ```bash
   git clone <your-repo-url>
   cd SIEMatic
   ```

2. **Create a virtual environment and install dependencies**
   ```bash
   python -m venv venv
   venv\Scripts\activate  # On Windows
   # Or on Mac/Linux: source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure settings**
   ```bash
   set DJANGO_SETTINGS_MODULE=SIEMatic.settings.web  # On Windows
   # Or on Mac/Linux: export DJANGO_SETTINGS_MODULE=SIEMatic.settings.web

   # Generate a Django secret key and export it before running any management command
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   set DJANGO_SECRET_KEY=<paste-generated-secret>  # On Windows
   # Or on Mac/Linux: export DJANGO_SECRET_KEY=<paste-generated-secret>
   ```

4. **Set up your database**
   ```bash
   python manage.py migrate
   ```

5. **Create a superuser (admin account)**
   ```bash
   python manage.py createsuperuser
   ```

6. **Run the development server**
   ```bash
   # Collect static files
   python manage.py collectstatic
   python manage.py runserver
   ```

7. **Run the production server (CherryPy)**
   ```bash
   python manage.py serve
   ```
   You can configure CherryPy with environment variables (see below) or command-line arguments.

8. **Run the Indexer**
   ```bash
   set DJANGO_SETTINGS_MODULE=SIEMatic.settings.indexer  # On Windows
   set INDEXER_HOSTNAME=127.0.0.1
   set INDEXER_PORT=7999
   # On Mac/Linux: use export instead of set
   python manage.py indexer
   ```
   Starts the ASGI server (Daphne) for WebSocket event ingestion.

10. **Create an Agent User**
    Log into the admin page at `/admin/project/customuser/` and add a user.
    Default permissions will be created for the user. This user will be used by the agent to authenticate with the indexer.
9. **Run the Agent**
   ```bash
   set INDEXER_USERNAME=<Username>
   set INDEXER_PASSWORD=<Password>
   set INDEXER_HOSTNAME=127.0.0.1
   set INDEXER_PORT=7999
   set DJANGO_SETTINGS_MODULE=SIEMatic.settings.agent  # On Windows
   # Or on Mac/Linux: export DJANGO_SETTINGS_MODULE=SIEMatic.settings.agent
   python manage.py agent
   ```
   Starts the agent service for plugin management and heartbeat.

10. **Run the Crawler**
   ```bash
   set DJANGO_SETTINGS_MODULE=SIEMatic.settings.crawler  # On Windows
   # Or on Mac/Linux: export DJANGO_SETTINGS_MODULE=SIEMatic.settings.crawler
   python manage.py run_crawlers
   ```
   Starts the crawler service for analytics, alerting, and automated data retention. Supports multiple concurrent crawler instances with different configurations.

## Deployment Options

SIEMatic supports multiple deployment methods for different environments.

### Local Development

Follow the Quick Start guide above for local development or single instance deployments.

### Using SIEMatic with Docker Compose

SIEMatic ships with a `docker-compose.yaml` for easy setup. Make sure to copy `.env.example` to `.env` and fill in required values.

#### Build and Start All Services
```bash
docker-compose up --build
```
This will build the images and start the web server, indexer, agent, crawler, and Postgres database.

#### Run Database Migrations (required after first start)
```bash
docker-compose exec siematic-web python manage.py migrate
```

#### Create a Superuser (for admin access)
```bash
docker-compose exec siematic-web python manage.py createsuperuser
```

#### Create a user (for the agent)
log into the admin page at `/admin/users/` and add a user. Default permissions will be created for the user.

The agent authenticates to the indexer as this user and needs permission to create events, which
regular users do not have. Add the agent's user to the **`Agent`** group (created automatically on
migrate) under `/admin/auth/group/` so its ingest requests to `/api/events/` aren't rejected with 403.

#### View Logs for All Services
```bash
docker-compose logs -f
```

#### Restart All Services
```bash
docker-compose restart
```

#### Stop and Remove All Containers
```bash
docker-compose down
```

Visit http://127.0.0.1:8000/ in your browser to access the web UI.

## Troubleshooting web access (local containers)

With the compose mapping `8000:8000` the web UI should be reachable at http://localhost:8000/ from the host running the containers. If you see a connection reset, refused, or a blank page, the commands below help narrow the problem down.

Basic checks

```bash
# Are the compose services up?
podman compose ps

# See running containers and find the web container name (e.g. siematic_siematic-web_1)
podman ps -a | grep -i siematic

# Tail the web logs (show startup errors, DB errors, import failures)
podman compose logs -f siematic-web
# or if you prefer the container name:
podman logs -f <container-name>

# Confirm the container exposes port 8000 on the host
podman port <container-name> 8000

# Quick HTTP check from the host
curl -v http://localhost:8000/
```

Django-specific checks (run inside the web container)

```bash
# Run Django system checks
podman compose exec siematic-web python manage.py check

# Run the test suite (helpful to reveal import/db/runtime issues)
podman compose exec siematic-web python manage.py test

# Confirm a process is listening on 8000 inside the container
podman compose exec siematic-web ss -lntp | grep -E ':8000\b|:8000\s'

# For interactive debugging, start the dev server binding 0.0.0.0:8000
# (useful if the packaged serve command isn't exposing the right interface)
podman compose exec -u root siematic-web python manage.py runserver 0.0.0.0:8000
```

Firewall / host network checks

```bash
# Does the host have a firewall blocking the port?
sudo ss -lntp | grep 8000 || true
sudo iptables -L -n | grep 8000 || true
# If using firewalld:
sudo firewall-cmd --list-all || true
```

Notes & tips

- If `podman compose logs` shows ImportError or lib-related errors, inspect the web container's image build output — a missing system library or a failed wheel build will surface there.
- If the container is running but `podman port` shows no mapping, ensure `ports:` is set in `docker-compose.yaml` and that you started compose with the same project name (some tools include the directory name in container names).
- When using a remote VM, replace `localhost` with the VM's IP or use an SSH tunnel:

```bash
ssh -L 8000:localhost:8000 user@remote-host
# then open http://localhost:8000 on your laptop
```

### Advanced: Automated Build & Packaging For Air-Gapped Systems

You can use `bootstrap.py` to automate building, packaging, and asset management for deployment to air-gapped systems.

After running the following commands, you will have a zip file under `./dist/` containing everything needed to deploy SIEMatic to an air-gapped system, including source code, Python interpreter, and dependencies:

- Clean build artefacts:
  ```bash
  python bootstrap.py clean
  ```
- Download and extract Python:
  ```bash
  python bootstrap.py download_python
  python bootstrap.py extract_python
  ```
- Install Python dependencies:
  ```bash
  python bootstrap.py run_pip_install
  ```
- Collect static files:
  ```bash
  python bootstrap.py collectstatic
  ```

## Migrating from django-components to static JS

This project previously used `django-components` for server-side components. To improve performance and simplify dependencies, UI components were migrated to static JavaScript files and plain Django includes. Key points:

- Move presentation HTML from component templates to `templates/components/...` and include them with `{% include %}`.
- Pass dynamic data (like `results`, `available_fields`, and `summary`) from the view context to the templates.
- Convert server-side component logic that prepared context into either view logic or small helper functions (see `search2.apps.generate_command_help_rows`).
- Load static JavaScript files in the page(s) where needed via `{% static %}` script tags (e.g., `search2/datatable.js`, `search2/chart.js`, `search2/visualization_selector.js`).
- Remove `{% load component_tags %}` and any use of `render_component` template tags.

Example: The chart and datatable components are now rendered by including `components/search2/chart.html` and `components/search2/datatable.html` and using `search2/chart.js` and `search2/datatable.js` for behavior.

This approach keeps templates server-rendered for static HTML while moving dynamic behavior and interactivity into client-side JS.
- Package everything:
  ```bash
  python bootstrap.py package
  ```

Or run all steps in sequence:
```bash
python bootstrap.py all
```

## Settings Configuration

SIEMatic uses role-based settings files for different deployment scenarios:

- `base.py`: Common settings shared across all roles
- `web.py`: Settings for the web server (Django app, admin, API)
- `agent.py`: Settings for the agent service (event collection plugins)
- `indexer.py`: Settings for the indexer service (WebSocket ingestion)
- `crawler.py`: Settings for the crawler service (analytics and alerting)

Use the appropriate settings file when running each component:

- Web server: `--settings=SIEMatic.settings.web`
- Agent: `--settings=SIEMatic.settings.agent`
- Indexer: `--settings=SIEMatic.settings.indexer`
- Crawler: `--settings=SIEMatic.settings.crawler`

This modular approach allows for optimized configurations per role and easier scaling across multiple machines.

Common environment variables:

- `DJANGO_SECRET_KEY`: required for every role; generate one with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`.
- `DJANGO_DEBUG`: enables Django debug mode. If `debug_toolbar` is not installed, SIEMatic skips loading it instead of crashing.
- `DJANGO_ALLOWED_HOSTS`: comma-separated hostnames for Django host validation.
- `SIEMATIC_TLS_ENABLED`: when `True`, enables Django's secure cookie, HTTPS redirect, and HSTS settings.
- `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `DEFAULT_FROM_EMAIL`: mail delivery settings. The default backend stays file-based for local development.

## Project Structure

- `settings/`: Project settings (base, web, agent, indexer, crawler)
- `project/`: Main app (custom user, views, forms, templates)
- `agent/`: Event collection agent and plugins
- `indexer/`: Indexer for event storage and retrieval
- `events/`: Event models, serializers, and extraction logic
- `search2/`: Search dashboard, summary statistics, and search pipeline
- `crawlers/`: Plugin-based analytics and alerting system
- `dashboards/`: (Currently under construction)
- `templates/`: Custom templates for authentication and other views
- `static/` and `media/`: Static and media files

## Search App


### Search Pipeline Commands

SIEMatic supports a modular search pipeline, where each stage is a command that transforms or analyzes your data. The main commands are:

#### 1. `search`
- **Purpose:** Query and filter events from the database or in-memory datasets.
- **Arguments:**
   - `--model`: Django model to query (default: `events.Event`)
   - `--using`: Database alias (default: `default`)
   - `--filter`: Add filter expressions (e.g., `field__gte=10`)
   - `--exclude`: Exclude expressions
   - `--select`: List of fields or expressions to project (Python list literal)
   - `--order-by`: List of fields to order by (Python list literal, prefix with `-` for descending)
   - `--limit`: Maximum number of results
- **Time Placeholders:** Arguments support dynamic time placeholders that are replaced with current datetime values. Use `{placeholder}` syntax in any argument value.
  - Available placeholders:
    - `{now}`: Current datetime
    - `{today}`: Current date
    - `{yesterday}`: Yesterday's date
    - `{this_minute}`: Start of current minute
    - `{last_minute}`: Start of last minute
    - `{this_hour}`: Start of current hour
    - `{last_hour}`: Start of last hour
    - `{this_day}`: Start of current day
    - `{last_day}`: Start of last day
    - `{this_week}`: Start of current week (Monday)
    - `{last_week}`: Start of last week (Monday)
    - `{this_month}`: Start of current month
    - `{last_month}`: Start of last month
    - `{this_year}`: Start of current year
    - `{last_year}`: Start of last year
    - `{last_7_days}`: 7 days ago
    - `{last_30_days}`: 30 days ago
    - `{timezone}`: Current timezone name
  - Examples: `--filter='created__gte={last_day}'` (events from last 24 hours), `--filter='created__date={yesterday}'` (events from yesterday)
- **Usage Example:**
   ```
   search --filter='created__gte="2025-01-01"' --select='["created","host"]' --order-by='["-created"]' --limit=100
   ```
   ```
   search --filter='created__gte={last_day}' --select='["created","host"]' --order-by='["-created"]' --limit=100
   ```

#### 2. `annotate`
- **Purpose:** Add computed fields to each result using expressions or database functions.
- **Arguments:**
   - `--set`: Annotation in the form `field=expression` (can use supported functions)
- **Usage Example:**
   ```
   annotate --set='avg_duration=Avg("duration")' --set='lower_host=Lower("host")'
   ```
- **Supported on:** Django QuerySets, pandas DataFrames, and Python records (dicts).

#### 3. `groupby` (aggregate)
- **Purpose:** Group results by fields and compute aggregations
- **Arguments:**
   - `--keys`: List of fields/expressions to group by (Python list/tuple literal)
   - `--out`: Name of the output aggregation field (default: `count`)
- **Usage Examples**
   ```
   groupby --keys='["host"]' --out='total_events'
   ```
- **Supported On:** All pipeline input types (QuerySets, DataFrames, records, etc.)

#### 4. `run_saved_search`
- **Purpose:** Run a SavedSearch by name, executing its stored query and returning results. Optionally accepts events to pass as input to the pipeline.
- **Arguments:**
   - `name`: The name of the SavedSearch to run
   - `--events`: Optional events data to use as the pipeline input
   - `--request`: Optional request object
- **Usage Example:**
   ```
   run_saved_search "My Search Name" --events=my_events_data
   ```
- **Supported on:** All pipeline input types (QuerySets, DataFrames, records, etc.)

#### 5. `explode`
- **Purpose:** Explode top-level keys of a JSON field into separate columns.
- **Arguments:**
   - `--field`: The field containing JSON data to explode (required)
- **Usage Example:**
   ```
   explode --field=data
   ```
- **Supported on:** Converts QuerySets/records to DataFrame; explodes JSON objects into prefixed columns (e.g., `data.key`).

You can use the following functions in `annotate`, `groupby`, and `select` expressions (where supported):

- **Aggregations:** `Avg`, `Sum`, `Count`, `Max`, `Min`, `StdDev`, `Variance`
- **String functions:** `Lower`, `Upper`, `Length`, `Trim`, `Replace`, `Reverse`, `Substr`
- **Math functions:** `Abs`, `Ceil`, `Floor`, `Exp`, `Ln`, `Log`, `Mod`, `Power`, `Round`, `Sign`, `Sin`, `Cos`, `Tan`, `Sqrt`, `Pi`, `Degrees`, `Radians`
- **Date/time functions:** `Now`, `TruncDate`, `TruncHour`, `TruncMinute`, `TruncMonth`, `TruncSecond`, `TruncYear`, `ExtractDay`, `ExtractMonth`, `ExtractYear`, etc.
- **JSON/Key-Transform:** `KT`, `JSONObject`
- **Other:** `F`, `Q`, `Func`, `Value`, `Greatest`, `Least`, `LPad`, `RPad`, `LTrim`, `RTrim`, `StrIndex`

**Note:** Not all functions are supported on all backends (Django QuerySet, pandas DataFrame, Python records). Most Django ORM functions work on QuerySets; some have equivalents for DataFrames and records.

---

### Example Pipeline

You can chain commands using the pipe (`|`) character:

```
search --filter='host="web01"' --select='["host","duration"]' | annotate --set='duration_min=Min("duration")' | groupby --keys='["host"]' --out='avg_duration'
```

This will:
1. Filter events for host "web01"
2. Annotate each result with the minimum duration
3. Group by host and compute the average duration

---

### Limitations

- JSON metrics must be stored as numeric types for aggregation functions (e.g., `Avg`) to work as expected
- DataFrame conversions rely on `pandas`/`django-pandas` and may consume significant memory on very large result sets
- All multi-valued flags must be Python literals
- Cross database joins, while possible and supported, can be very slow, cpu intensive and memory intensive if the result set is too large. 
- **Summary Statistics Limitations**:
  - Date detection relies on common date formats (ISO, US, European) and may not detect all custom formats
  - Very large datasets may experience slower performance during statistical calculations
  - Mode calculation for numeric data may fail if all values are unique (returns None)
  - Text analysis is limited to the first 3 most common values for display

## Crawlers

SIEMatic includes a plugin-based crawler system for continuous analytics and alerting on event data. Crawlers run as background processes, scanning events to generate findings with MITRE ATT&CK mappings (Not all plugins will be mapped to MITRE ATT&CK).

### Configuration

Configure crawlers in Django settings:

```python
CRAWLER_PLUGINS = [
    'crawlers.plugins.failed_login_crawler.FailedLoginCrawler',
    # Add more plugins
]

CRAWLER_CONFIGS = {
    'failed_login_crawler': {
        'type': 'daemon',  # 'daemon' or 'scheduled'
        'restart': True,   # True (infinite), False (none), or int (max attempts)
        'interval': 60,    # Scan interval in seconds (for daemon)
        'schedule': '*/5 * * * *',  # Cron schedule (for scheduled, requires croniter)
        'realert_cooldown': 60 * 60 * 24,  # Seconds to prevent re-alerting same event
        'db_alias': 'default',
    },
}
```

### Running Crawlers

- **Service Mode**: `python manage.py run_crawlers` (runs indefinitely, monitoring processes and managing schedules).
- **Test Single Plugin**: `python manage.py run_crawlers --plugin failed_login_crawler`.

### Plugin Development

Create plugins in `crawlers/plugins/` inheriting from `BaseCrawlerPlugin`. Implement `run()` for daemon loops or single scans.

Example: `FailedLoginCrawler` detects "failed login" in event data, creates findings with Credential Access: Brute Force mapping, and respects time windows and cooldowns.

Findings are stored in the `Finding` model and viewable in Django admin.

## Performance Tuning and Scaling

SIEMatic is designed for extensibility, but high-volume event ingestion or analysis can require tuning. Below are key strategies for scaling.

### Database Scaling
- **Multiple Databases**: Use Django's database aliases (e.g., `db_alias` in configs) to distribute load. Agents/indexers can write to separate DBs, and searches/crawlers can query across them via Pandas joins (planned).
- **Upgrade from SQLite**: For production, switch to PostgreSQL for better concurrency and indexing. Update `DATABASES` in settings.
- **Indexing**: For PostgreSQL, add a BRIN index on `events_event.created` for efficient time-based queries:
  ```sql
  CREATE INDEX CONCURRENTLY idx_events_created_brin ON events_event USING brin (created);
  ```
  This speeds up reads/writes for time-windowed operations (e.g., crawler scans).

### Crawler and Worker Scaling
- **Horizontal Scaling**: Crawlers are stateless and config-driven. Run multiple `run_crawlers` instances on separate nodes with different `CRAWLER_CONFIGS` (e.g., one per DB alias). No coordination needed since execution isn't tracked in DB.
- **Load Balancing**: Distribute agents/indexers across nodes using different DB aliases to avoid write bottlenecks.

### General Django Scaling
- **Web Servers**: Use Gunicorn or uWSGI with multiple workers for the Django app.
- **Caching**: Add Redis/Memcached for session/query caching.
- **Async Tasks**: For heavy searches, integrate Django-Q or Celery.
- **Monitoring**: Profile with Django Debug Toolbar; monitor DB with pg_stat_statements (Postgres).

Start with single-node Postgres, then scale DBs/crawlers as load grows.

## Customization

- Update `settings/web.py` for your production database and email (web server)
- Update `settings/agent.py` for agent-specific configurations
- Update `settings/indexer.py` for indexer-specific configurations
- Update `settings/crawler.py` for crawler-specific configurations
- Add fields to registration/profile in `project/forms.py`
- Swap the Bahunya CSS in `base.html` for your own style

## Security Notes

- CSRF protection on all forms
- Permission checks on model and traversal
- No sensitive data in repository

## License

SIEMatic is licensed under the Business Source License 1.1. See the root
[LICENSE](LICENSE) file for the full license text and Additional Use Grant.

Free to use for Individuals, as well as Non-profit and Educational institutions with no feature restrictions.

Business users must obtain a business license. To obtain a business license, email sales@mcindi.com.
