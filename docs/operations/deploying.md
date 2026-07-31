---
title: Deploying
---

# Deploying

The repository's `docker-compose.yaml` runs PostgreSQL and the SIEMatic web,
indexer, agent, and crawler services. The application services share one image
and one database configuration.

## Prepare configuration

Copy the example environment file and replace every placeholder or blank
credential:

```bash
cp .env.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Set the generated value as `DJANGO_SECRET_KEY`, choose strong and distinct
`DATABASE_PASSWORD` and `INDEXER_PASSWORD` values. Make sure that
`INDEXER_USERNAME` names a dedicated account that will be placed in the
`Agent` group. Keep `.env` out of source control.

For local Compose testing, generate the gitignored certificate files expected
by the volume mounts:

```bash
python tools/gen_dev_cert.py
```

The generated certificate covers localhost and the Compose service names. In
production, replace it with a certificate and private key issued by a CA trusted
by browsers and agents. Set `DJANGO_ALLOWED_HOSTS` for the actual hostnames and
leave `DJANGO_DEBUG=False`.

## Start and initialize

Build and start the services:

```bash
docker compose up --build -d
docker compose ps
```

Apply database migrations and create the first administrator:

```bash
docker compose exec siematic-web python manage.py migrate
docker compose exec siematic-web python manage.py createsuperuser
```

Provision the agent identity in Django admin and add it to the `Agent` group.
The username and password must match `INDEXER_USERNAME` and `INDEXER_PASSWORD`
in `.env`. Then restart the agent and inspect its logs:

```bash
docker compose restart siematic-agent
docker compose logs -f siematic-agent
```

The web interface is mapped to `https://localhost:8000/` by the supplied
TLS-enabled configuration. A reverse proxy can terminate public TLS, but the
certificate paths and `SIEMATIC_TLS_ENABLED` settings must remain consistent
with the chosen topology.

## Routine Compose commands

```bash
docker compose logs -f
docker compose restart
docker compose down
```

`docker compose down` preserves the named PostgreSQL volume. Do not add `-v`
unless permanent database removal is intentional and a verified backup exists.

## Air-gapped package

`bootstrap.py` can assemble source, a standalone Python interpreter,
dependencies, and collected static files into a zip under `dist/`:

```bash
python bootstrap.py clean
python bootstrap.py stage_for_package
python bootstrap.py download_python
python bootstrap.py extract_python
python bootstrap.py run_pip_install
python bootstrap.py collectstatic
python bootstrap.py package
```

Run the complete sequence with `python bootstrap.py all`. Build for the same OS
and architecture as the destination. Transfer the archive through the approved
channel. Supply secrets and trusted certificates separately.

## Vendored browser assets

Browser dependencies are committed under `static/vendor/` for offline use.
Their source URLs, versions, and SHA-256 hashes are in
`tools/vendor_manifest.json`. Verify the recorded assets with:

```bash
python tools/vendor_assets.py
```

To update within the supported version series and rewrite hashes, run
`python tools/vendor_assets.py --update`. Then collect static files and run the
test suite. Commit the manifest and changed assets together.
