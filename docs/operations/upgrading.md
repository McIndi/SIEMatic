---
title: Upgrading
---

# Upgrading

Upgrade first in an environment restored from a recent production backup. Read
the repository changes, note dependency and settings changes, and plan a
maintenance window when migrations or image replacement can interrupt service.

## Docker Compose procedure

1. Record the deployed revision and back up PostgreSQL, `.env`, certificates,
   and local settings or plugins.
2. Fetch and check out the intended release or commit.
3. Compare `.env.example` and `docker-compose.yaml` with the deployed versions.
4. Build the new image without starting it:

   ```bash
   docker compose build
   ```

5. Stop application services, leaving the database available, and apply
   migrations with the new web image:

```bash
docker compose stop siematic-agent siematic-indexer siematic-crawler siematic-web
docker compose run --rm siematic-web python manage.py migrate
docker compose run --rm siematic-web python manage.py check
```

6. Start all services and inspect status and logs:

```bash
docker compose up -d
docker compose ps
docker compose logs --tail=200
```

Validate login, ingestion, search, saved searches, dashboards, findings, and
alerts. Do not remove old images or backups until the acceptance checks pass.

Database migrations are not assumed reversible. If rollback is necessary,
restore both the previous application revision and the matching database backup
rather than running ad hoc reverse migrations against production.
