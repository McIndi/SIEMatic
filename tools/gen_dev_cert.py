#!/usr/bin/env python
"""Generate a self-signed development certificate for SIEMatic."""

import argparse
import ipaddress
import os
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
except ImportError:
    sys.exit(
        "cryptography is required. Install SIEMatic's dependencies with "
        "`pip install -r requirements.txt`."
    )


DEFAULT_NAMES = (
    'localhost',
    '127.0.0.1',
    '::1',
    'siematic-web',
    'siematic-indexer',
)


def _subject_alt_name(value):
    try:
        return x509.IPAddress(ipaddress.ip_address(value))
    except ValueError:
        return x509.DNSName(value)


def generate_certificate(cert_path, key_path, names, force=False):
    """Write a PEM certificate and private key, returning their paths."""
    cert_path = Path(cert_path)
    key_path = Path(key_path)
    existing = [path for path in (cert_path, key_path) if path.exists()]
    if existing and not force:
        paths = ', '.join(str(path) for path in existing)
        raise FileExistsError(
            f'Refusing to overwrite {paths}; pass --force to replace them.'
        )

    cert_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.parent.mkdir(parents=True, exist_ok=True)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    common_name = names[0]
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'SIEMatic Development'),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=825))
        .add_extension(
            x509.SubjectAlternativeName([_subject_alt_name(name) for name in names]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )

    key_path.write_bytes(private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def main():
    project_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--cert',
        type=Path,
        default=project_root / 'certs' / 'siematic.crt',
        help='Certificate output path.',
    )
    parser.add_argument(
        '--key',
        type=Path,
        default=project_root / 'certs' / 'siematic.key',
        help='Private-key output path.',
    )
    parser.add_argument(
        '--name',
        action='append',
        dest='names',
        help='DNS name or IP SAN. May be repeated.',
    )
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()

    names = list(dict.fromkeys(args.names or (*DEFAULT_NAMES, socket.gethostname())))
    try:
        cert_path, key_path = generate_certificate(
            args.cert, args.key, names, force=args.force
        )
    except FileExistsError as exc:
        parser.error(str(exc))

    print(f'Certificate: {cert_path}')
    print(f'Private key: {key_path}')
    print(f'Subject alternative names: {", ".join(names)}')


if __name__ == '__main__':
    main()
