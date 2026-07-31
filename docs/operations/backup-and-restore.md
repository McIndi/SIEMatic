---
title: Backup and Restore
---

# Backup and Restore

A recoverable SIEMatic installation needs the database, deployment
configuration, trusted certificates, and any locally changed settings or
plugins. Keep secrets and private keys in an access-controlled backup system,
not in the source archive.

## PostgreSQL Compose deployment

Create a logical backup from the database container:

```bash
docker compose exec -T siematic-db pg_dump -U siematic -d siematic -Fc > siematic.dump
```

Replace the username and database with the values in `.env`. Make sure that the
file is not empty. Regularly test restoration in an isolated environment.

To restore, stop application writers, create an empty target database, and run:

```bash
docker compose exec -T siematic-db pg_restore -U siematic -d siematic --clean --if-exists < siematic.dump
docker compose exec siematic-web python manage.py migrate
```

`--clean` overwrites objects in the target database. Use it only after checking
that the target is the intended restore environment.

## SQLite development

Stop `rundev` before copying `db.sqlite3`. Restore it only into a compatible
checkout, then run migrations. A live file copy is not a reliable backup.

## Portable Django data

`dumpdata` and `loaddata` can move whole-project Django records when a logical
JSON fixture is useful:

```bash
python manage.py dumpdata --natural-foreign --natural-primary -o siematic.json
python manage.py loaddata siematic.json
```

This is project-level import/export, not per-saved-search or per-dashboard
export. Database-native backups are preferred for disaster recovery.

After each restore, run `manage.py check`. Make sure that all migrations are
complete. Sign in and run a known search. Inspect dashboards and findings. Make
sure that an agent can ingest a test event.
