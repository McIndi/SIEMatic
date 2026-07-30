"""Download and verify the frontend assets committed under ``static/vendor``.

Normal runs use the versions and SHA-256 digests recorded in
``tools/vendor_manifest.json``.  ``--update`` selects the newest stable release
in each package's supported version series, downloads it, and rewrites the
manifest with the new versions and digests.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import tempfile
from urllib.parse import quote

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bootstrap import get_file_sha256


DEFAULT_MANIFEST = ROOT / "tools" / "vendor_manifest.json"
DEFAULT_DESTINATION = ROOT / "static" / "vendor"
NPM_REGISTRY = "https://registry.npmjs.org"
JSDELIVR = "https://cdn.jsdelivr.net/npm"
STABLE_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def version_key(version: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in version.split("."))  # type: ignore[return-value]


def latest_supported_version(package: dict) -> str:
    npm_name = package["npm"]
    response = requests.get(
        f"{NPM_REGISTRY}/{quote(npm_name, safe='@')}",
        timeout=30,
    )
    response.raise_for_status()
    versions = [
        version
        for version in response.json()["versions"]
        if STABLE_VERSION.fullmatch(version)
        and version.startswith(package["version_prefix"])
    ]
    if not versions:
        raise RuntimeError(
            f"No stable {npm_name} release matches "
            f"{package['version_prefix']!r}"
        )
    return max(versions, key=version_key)


def asset_url(npm_name: str, version: str, source: str) -> str:
    return f"{JSDELIVR}/{npm_name}@{version}/{source}"


def destination_path(destination: pathlib.Path, relative_path: str) -> pathlib.Path:
    candidate = (destination / relative_path).resolve()
    destination = destination.resolve()
    if destination not in candidate.parents:
        raise ValueError(f"Asset path escapes destination: {relative_path}")
    return candidate


def download(url: str, target: pathlib.Path) -> None:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    target.write_bytes(response.content)


def vendor_assets(
    manifest_path: pathlib.Path,
    destination: pathlib.Path,
    update: bool = False,
) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    destination.mkdir(parents=True, exist_ok=True)

    for package_name, package in manifest["packages"].items():
        if update:
            package["version"] = latest_supported_version(package)

        version = package["version"]
        for asset in package["assets"]:
            url = asset_url(package["npm"], version, asset["source"])
            target = destination_path(destination, asset["path"])
            target.parent.mkdir(parents=True, exist_ok=True)

            with tempfile.NamedTemporaryFile(delete=False) as temporary:
                temporary_path = pathlib.Path(temporary.name)
            try:
                download(url, temporary_path)
                actual_hash = get_file_sha256(temporary_path)
                if update:
                    asset["sha256"] = actual_hash
                elif actual_hash != asset["sha256"]:
                    raise RuntimeError(
                        f"Checksum mismatch for {package_name}/{asset['path']}: "
                        f"expected {asset['sha256']}, got {actual_hash}"
                    )
                temporary_path.replace(target)
                print(f"Vendored {package_name} {version}: {asset['path']}")
            finally:
                temporary_path.unlink(missing_ok=True)

    if update:
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Updated {manifest_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download checksum-pinned frontend assets."
    )
    parser.add_argument(
        "--manifest",
        type=pathlib.Path,
        default=DEFAULT_MANIFEST,
        help="Vendor manifest path",
    )
    parser.add_argument(
        "--destination",
        type=pathlib.Path,
        default=DEFAULT_DESTINATION,
        help="Directory in which to place assets",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Use latest supported releases and rewrite checksums",
    )
    args = parser.parse_args()
    vendor_assets(args.manifest.resolve(), args.destination.resolve(), args.update)


if __name__ == "__main__":
    main()
