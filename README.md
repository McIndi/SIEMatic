# SIEMatic

SIEMatic is a fair-sourced observability platform for collecting, indexing,
searching, and analyzing security events with Django. It includes pluggable
agents, an authenticated WebSocket indexer, a pipeline search language, saved
searches, dashboards, crawler analytics, findings, alerts, retention policies,
and REST APIs.

> [!WARNING]
> **Early-release alpha.** SIEMatic is under active development and is shipping as an alpha. Interfaces, data formats, configuration, and features may change without notice, and stability is not guaranteed. Evaluate it in non-production environments. If you need to depend on SIEMatic for a production workload, contact **sales@mcindi.com** for a paid support contract.

Read the full documentation at **https://mcindi.com/SIEMatic/**.

## Quick start

Python 3.12 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py rundev
```

Open `https://localhost:8000/`. The local certificate is self-signed. For setup,
deployment, administration, search syntax, plugin development, and API details,
see the [documentation](https://mcindi.com/siematic/). `rundev` creates the
`siematic-admin` development superuser and writes its generated password to
`rundev-superuser.txt`. The ignored file is overwritten with a new password
each time the command starts.

## License

SIEMatic is distributed under the Business Source License 1.1 with an Additional
Use Grant for qualifying personal, nonprofit, and educational use. See
[LICENSE](LICENSE) for the authoritative terms, including the Change Date and
Change License. Contact
`sales@mcindi.com` for commercial licensing.
