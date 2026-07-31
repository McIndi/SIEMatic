---
title: Troubleshooting
---

# Troubleshooting

## Web interface is unavailable

The supplied mapping exposes the TLS-enabled web service on port 8000. Start
with service state and logs:

```bash
docker compose ps
docker compose logs --tail=200 siematic-web
docker compose port siematic-web 8000
curl -vk https://localhost:8000/accounts/login/
```

Run Django diagnostics inside the web container:

```bash
docker compose exec siematic-web python manage.py check
docker compose exec siematic-web python manage.py showmigrations
```

Common causes include a missing certificate volume or an invalid
`DJANGO_SECRET_KEY`. Other causes include an incomplete `DJANGO_ALLOWED_HOSTS`
or a database connection failure. The connection also fails if you use
`http://` when the supplied Compose service expects `https://`.

For a remote host, connect to its published address or use a temporary tunnel:

```bash
ssh -L 8000:localhost:8000 user@remote-host
```

Then browse to `https://localhost:8000/` locally.

## Agent sends no events

```bash
docker compose logs --tail=200 siematic-agent siematic-indexer
docker compose exec siematic-agent python -c "import os; print(os.getenv('INDEXER_HOSTNAME'), os.getenv('INDEXER_PORT'))"
```

Make sure that the indexer username exists and belongs to the `Agent` group.
Make sure that it matches the agent environment. For TLS,
`INDEXER_CA_BUNDLE` must name a readable
CA or server certificate that verifies the indexer's hostname. Verification is
not disabled when the bundle is absent. The system trust roots are used instead.

## Crawlers or alerts do not run

```bash
docker compose logs --tail=200 siematic-crawler
docker compose exec siematic-crawler python manage.py run_crawlers --plugin failed_login_crawler
```

Check that the configured crawler instance is enabled, its name matches a
loaded plugin, and a scheduled instance has valid cron syntax. If you use the
default file backend, inspect `sent_emails/`. For a production
backend, make sure that the SMTP variables are correct.

## Misleading container health

The image-level health check probes the web port and is inherited by the other
application services. Agent, indexer, and crawler containers can therefore
report `unhealthy` while their processes are working. Use process-specific logs
and functional checks. See [Known Limitations](../reference/known-limitations.md).

## Run the test suite

```bash
docker compose exec siematic-web python manage.py test --settings SIEMatic.settings.web
```

For local development, activate the virtual environment and run the same
management command without Compose.
