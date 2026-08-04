#!/usr/bin/env python
"""Run a role-specific health probe for a SIEMatic container."""

import argparse
import os
import socket
import ssl
import sys
import urllib.error
import urllib.request


TRUE_VALUES = {"1", "true", "yes", "on"}


def web_is_healthy():
    """Return whether the local web service responds without a server error."""
    tls_enabled = os.getenv("SIEMATIC_TLS_ENABLED", "").strip().lower() in TRUE_VALUES
    scheme = "https" if tls_enabled else "http"
    port = int(os.getenv("CHERRYPY_PORT", "8000"))
    url = f"{scheme}://127.0.0.1:{port}/accounts/login/"
    context = None
    if tls_enabled:
        context = ssl.create_default_context()
        # This local liveness probe checks the server, not its public identity.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(url, timeout=4, context=context) as response:
            return response.status < 500
    except urllib.error.HTTPError as error:
        return error.code < 500


def indexer_is_healthy():
    """Return whether the local indexer accepts TCP connections."""
    port = int(os.getenv("INDEXER_PORT", "5001"))
    with socket.create_connection(("127.0.0.1", port), timeout=4):
        return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("web", "indexer"))
    args = parser.parse_args(argv)

    probes = {
        "web": web_is_healthy,
        "indexer": indexer_is_healthy,
    }
    try:
        healthy = probes[args.role]()
    except (OSError, ValueError) as error:
        print(f"{args.role} health probe failed: {error}", file=sys.stderr)
        return 1
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
