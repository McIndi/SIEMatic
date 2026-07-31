---
title: Quickstart
---

# Quickstart

The `rundev` management command starts a complete local SIEMatic environment
with SQLite and a self-signed certificate. It is intended for development and
evaluation, not production.

!!! warning "Early-release alpha"
    SIEMatic is an alpha. It is suitable for evaluation and development, not for
    production reliance. For a production support contract, contact
    **sales@mcindi.com**.

## Prerequisites

- Python 3.12 or newer (CI exercises Python 3.13 and 3.14)
- Git and pip

## Install

Clone the repository, create a virtual environment, and install the runtime
dependencies:

```bash
git clone https://github.com/mcindi/SIEMatic.git
cd SIEMatic
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Or on macOS and Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## Start the stack

```bash
python manage.py rundev
```

No `.env` file is required. The command uses `db.sqlite3`, applies migrations,
collects static assets, and creates `certs/siematic.crt` and
`certs/siematic.key` when they are absent. It also creates or updates the
`siematic-admin` development superuser with a random password. The command
writes the credentials to `rundev-superuser.txt` in the repository root. It
then supervises:

- the HTTPS web application at `https://localhost:8000/`
- the TLS WebSocket indexer at `https://localhost:8001/`
- an authenticated agent running the cross-platform sysmon plugin.

The browser will warn about the self-signed development certificate. After
accepting it, use the username and password in `rundev-superuser.txt` to sign
in. Allow several seconds for CPU, memory, disk, and network events to become
searchable. Press Ctrl+C to stop the process tree.

`rundev-superuser.txt` is ignored by Git and is overwritten with a newly
generated password each time `rundev` starts. Treat it as a secret and use this
account only in the local development environment.

When either port is occupied, choose alternatives:

```bash
python manage.py rundev --web-port 8443 --indexer-port 8444
```

## Open the administration site

Sign in at `https://localhost:8000/admin/` with the generated credentials in
`rundev-superuser.txt`. See [User and Permission
Management](operations/user-and-permission-management.md) before provisioning
ordinary users or agent service accounts.

## Try a search

Open `/search2/` and enter:

```pipeline
search --filter='index="sysmon"' --order-by='["-created"]' --limit=20
```

Use the command help displayed beside the search form or consult the generated
[Search Command Reference](reference/search-commands.md).
