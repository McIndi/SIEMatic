"""
SIEMatic Bootstrap Script
Adapted from Delve, simplified for SIEMatic without frontend build.
"""
import sys
import os
import re
import shlex
import shutil
import subprocess
import logging
import argparse
import pathlib
import requests
import hashlib
from typing import List

__here__ = pathlib.Path(__file__).parent.resolve()

# --- Utility Functions ---
def setup_logging(log_level, log_file=None):
    log_file = log_file or (__here__ / "bootstrap.log")
    log_level_value = getattr(logging, log_level)
    formatter = logging.Formatter("%(levelname)s: %(name)s: %(process)d: %(threadName)s: %(module)s: %(pathname)s: %(funcName)s: %(lineno)d: %(asctime)s: %(message)s")

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level_value)

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(log_level_value)
    sh.setFormatter(formatter)
    root_logger.addHandler(sh)

    fh = logging.FileHandler(log_file, mode="a")
    fh.setLevel(log_level_value)
    fh.setFormatter(formatter)
    root_logger.addHandler(fh)

def get_platform():
    if sys.platform.startswith('linux'):
        return 'linux', 'unknown-linux-gnu'
    elif sys.platform.startswith('win'):
        return 'windows', 'windows-msvc'
    elif sys.platform.startswith('darwin'):
        return 'darwin', 'apple-darwin'
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")

def rglob_patterns(base: pathlib.Path, patterns: List[str]):
    for pattern in patterns:
        yield from base.rglob(pattern)

def get_file_sha256(p):
    sha256 = hashlib.sha256()
    with open(p, 'rb') as fp:
        while True:
            data = fp.read(65536)
            if not data:
                break
            sha256.update(data)
    return sha256.hexdigest()

# --- Subcommand Implementations ---
def clean(args):
    patterns = [
        "build",
        "dist",
        "__pycache__",
        "*.log",
        "build.log"
    ]
    logging.info(f"Cleaning patterns: {patterns}")
    for match in rglob_patterns(args.path, patterns):
        if match.name == "bootstrap.log":
            continue
        if match.is_file():
            logging.info(f"Removing file: {match}")
            match.unlink()
        elif match.is_dir():
            logging.info(f"Removing directory: {match}")
            shutil.rmtree(match, ignore_errors=True)

def download_python(args):
    plat, plat_str = get_platform()
    target_dir = args.target_dir.resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    latest_release_url = "https://raw.githubusercontent.com/indygreg/python-build-standalone/latest-release/latest-release.json"
    tag = requests.get(latest_release_url).json()["tag"]
    assets = requests.get(f"https://api.github.com/repos/indygreg/python-build-standalone/releases/tags/{tag}", headers={'X-GitHub-Api-Version': '2022-11-28', 'Accept': 'application/vnd.github+json'}).json()["assets"]
    release_names = [a["name"] for a in assets]
    filtered = [n for n in release_names if "install_only_stripped" in n and plat_str in n and "x86_64" in n]
    filtered = [n for n in filtered if not re.search(r'cpython-(\d+\.\d+\.\d+)[a-zA-Z]', n)]
    def extract_version(name):
        m = re.search(r'cpython-(\d+\.\d+\.\d+)', name)
        return tuple(map(int, m.group(1).split('.'))) if m else (0, 0, 0)
    filtered.sort(key=extract_version, reverse=True)
    if not filtered:
        logging.error(f"No suitable release found for platform: {plat}")
        sys.exit(1)
    release_file = filtered[0]
    hash_file = "SHA256SUMS"
    def asset_url(name):
        for a in assets:
            if a["name"] == name:
                return a["url"]
        return None
    hash_file_url = asset_url(hash_file)
    release_file_url = asset_url(release_file)
    asset_headers = {'X-GitHub-Api-Version': '2022-11-28', 'Accept': 'application/octet-stream'}
    hash_file_path = target_dir.joinpath(hash_file)
    release_file_path = target_dir.joinpath(release_file)
    with open(hash_file_path, "wb") as fp:
        fp.write(requests.get(hash_file_url, headers=asset_headers).content)
    with open(release_file_path, "wb") as fp:
        fp.write(requests.get(release_file_url, headers=asset_headers).content)
    logging.info(f"Downloaded {release_file} and {hash_file} to {target_dir}")
    hash_hex = None
    for line in hash_file_path.read_text().splitlines():
        if release_file in line:
            hash_hex = line.split()[0]
            break
    if not hash_hex:
        logging.error(f"Could not find hash for {release_file} in {hash_file}")
        sys.exit(1)
    actual_hash = get_file_sha256(release_file_path)
    if hash_hex != actual_hash:
        logging.error(f"Checksum mismatch for {release_file}: expected {hash_hex}, got {actual_hash}")
        sys.exit(1)
    logging.info(f"Checksum verified for {release_file}")

def extract_python(args):
    plat, _ = get_platform()
    logging.info(f"Extracting Python for platform: {plat}")
    downloads_dir = args.downloads_dir.resolve()
    assemble_dir = args.assemble_dir.resolve()
    assemble_dir.mkdir(parents=True, exist_ok=True)
    tarballs = list(downloads_dir.glob("cpython*install_only_stripped*tar.gz"))
    if not tarballs:
        logging.error(f"No Python tarball found in {downloads_dir}")
        sys.exit(1)
    tarball = tarballs[0]
    logging.info(f"Extracting {tarball} to {assemble_dir}")
    shutil.unpack_archive(tarball, assemble_dir)
    logging.info(f"Extracted Python to {assemble_dir}")

def run_pip_install(args):
    python_executable = args.python_executable or (args.assemble_dir / "python" / ("bin/python3" if os.name != "nt" else "python.exe"))
    requirements = args.requirements or (__here__ / "requirements.txt")
    logging.info(f"Installing Python dependencies using {python_executable} and {requirements}")
    result = subprocess.run([str(python_executable), "-m", "pip", "install", "--upgrade", "pip"], check=True, capture_output=True, text=True)
    logging.info(result.stdout)
    if result.stderr:
        logging.warning(result.stderr)
    result = subprocess.run([str(python_executable), "-m", "pip", "install", "-r", str(requirements)], check=True, capture_output=True, text=True)
    logging.info(result.stdout)
    if result.stderr:
        logging.warning(result.stderr)
    logging.info("Python dependencies installed")

def collectstatic(args):
    python_executable = args.python_executable or (args.assemble_dir / "python" / ("bin/python3" if os.name != "nt" else "python.exe"))
    manage_py = args.manage_py
    logging.info(f"Running collectstatic using {python_executable} {manage_py}")
    cmd = [str(python_executable), str(manage_py), "collectstatic", "--no-input"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logging.error(f"collectstatic failed with exit code {result.returncode}")
        logging.error(result.stderr)
        logging.error(result.stdout)
        sys.exit(result.returncode)
    logging.info(result.stdout)
    if result.stderr:
        logging.warning(result.stderr)

def stage_for_package(args):
    src_root = args.src_root
    dest_root = args.dest_root
    dest_root.mkdir(parents=True, exist_ok=True)
    logging.info(f"Staging files from {src_root} to {dest_root}")
    # Copy everything except build artifacts
    excludes = ["build", "dist", "__pycache__", "*.log", "node_modules", ".git", ".env"]
    for item in src_root.iterdir():
        if item.name in excludes or any(item.match(p) for p in excludes):
            continue
        if item.is_file():
            shutil.copy2(item, dest_root)
        elif item.is_dir():
            shutil.copytree(item, dest_root / item.name, dirs_exist_ok=True)
    logging.info("Files staged for packaging")

def package(args):
    assemble_dir = args.assemble_dir
    dist_dir = args.dist_dir
    dist_dir.mkdir(parents=True, exist_ok=True)
    output = args.output or (dist_dir / "siematic-deployment.zip")
    logging.info(f"Creating zip package {output} from {assemble_dir}")
    shutil.make_archive(str(output.with_suffix('')), 'zip', assemble_dir)
    logging.info(f"Package created: {output}")

def run_all(args):
    clean_args = argparse.Namespace(path=args.clean_path)
    clean(clean_args)
    stage_args = argparse.Namespace(src_root=args.stage_src_root, dest_root=args.stage_dest_root)
    stage_for_package(stage_args)
    download_args = argparse.Namespace(target_dir=args.download_target_dir)
    download_python(download_args)
    extract_args = argparse.Namespace(downloads_dir=args.extract_downloads_dir, assemble_dir=args.extract_assemble_dir)
    extract_python(extract_args)
    pip_args = argparse.Namespace(python_executable=args.pip_python_executable, requirements=args.pip_requirements, assemble_dir=args.pip_assemble_dir)
    run_pip_install(pip_args)
    static_args = argparse.Namespace(python_executable=args.static_python_executable, manage_py=args.static_manage_py, assemble_dir=args.static_assemble_dir)
    collectstatic(static_args)
    package_args = argparse.Namespace(assemble_dir=args.package_assemble_dir, dist_dir=args.package_dist_dir, output=args.package_output)
    package(package_args)

def main():
    parser = argparse.ArgumentParser(description="SIEMatic Bootstrap Script")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Logging level")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # clean
    clean_parser = subparsers.add_parser("clean", help="Clean build artifacts")
    clean_parser.add_argument("--path", type=pathlib.Path, default=__here__, help="Base path to clean")
    clean_parser.set_defaults(func=clean)

    # download_python
    dp_parser = subparsers.add_parser("download_python", help="Download Python standalone")
    dp_parser.add_argument("--target-dir", type=pathlib.Path, default=__here__/"build"/"downloads", help="Download directory")
    dp_parser.set_defaults(func=download_python)

    # extract_python
    ep_parser = subparsers.add_parser("extract_python", help="Extract Python")
    ep_parser.add_argument("--downloads-dir", type=pathlib.Path, default=__here__/"build"/"downloads", help="Downloads directory")
    ep_parser.add_argument("--assemble-dir", type=pathlib.Path, default=__here__/"build"/"assemble", help="Assemble directory")
    ep_parser.set_defaults(func=extract_python)

    # run_pip_install
    pip_parser = subparsers.add_parser("run_pip_install", help="Install Python dependencies")
    pip_parser.add_argument("--python-executable", type=pathlib.Path, help="Python executable")
    pip_parser.add_argument("--requirements", type=pathlib.Path, help="Requirements file")
    pip_parser.add_argument("--assemble-dir", type=pathlib.Path, default=__here__/"build"/"assemble", help="Assemble directory")
    pip_parser.set_defaults(func=run_pip_install)

    # collectstatic
    static_parser = subparsers.add_parser("collectstatic", help="Run manage.py collectstatic")
    static_parser.add_argument("--python-executable", type=pathlib.Path, help="Python executable")
    static_parser.add_argument("--manage-py", type=pathlib.Path, default=__here__/"build"/"assemble"/"manage.py", help="manage.py location")
    static_parser.add_argument("--assemble-dir", type=pathlib.Path, default=__here__/"build"/"assemble", help="Assemble directory")
    static_parser.set_defaults(func=collectstatic)

    # stage_for_package
    stage_parser = subparsers.add_parser("stage_for_package", help="Stage files for packaging")
    stage_parser.add_argument("--src-root", type=pathlib.Path, default=__here__, help="Source root")
    stage_parser.add_argument("--dest-root", type=pathlib.Path, default=__here__/"build"/"assemble", help="Destination root")
    stage_parser.set_defaults(func=stage_for_package)

    # package
    package_parser = subparsers.add_parser("package", help="Create zip package")
    package_parser.add_argument("--assemble-dir", type=pathlib.Path, default=__here__/"build"/"assemble", help="Assemble directory")
    package_parser.add_argument("--dist-dir", type=pathlib.Path, default=__here__/"dist", help="Dist directory")
    package_parser.add_argument("--output", type=pathlib.Path, help="Output zip file")
    package_parser.set_defaults(func=package)

    # all
    all_parser = subparsers.add_parser("all", help="Run all steps")
    # Clean args
    all_parser.add_argument("--clean-path", type=pathlib.Path, default=__here__, help="Base path to clean from")
    # Download Python args
    all_parser.add_argument("--download-target-dir", type=pathlib.Path, default=__here__/"build"/"downloads", help="Where to download Python")
    # Extract Python args
    all_parser.add_argument("--extract-downloads-dir", type=pathlib.Path, default=__here__/"build"/"downloads", help="Where Python tarball is")
    all_parser.add_argument("--extract-assemble-dir", type=pathlib.Path, default=__here__/"build"/"assemble", help="Where to extract Python")
    # pip install args
    all_parser.add_argument("--pip-python-executable", type=pathlib.Path, help="Python executable to use for pip install")
    all_parser.add_argument("--pip-requirements", type=pathlib.Path, help="Requirements file to use for pip install")
    all_parser.add_argument("--pip-assemble-dir", type=pathlib.Path, default=__here__/"build"/"assemble", help="Where Python is extracted for pip install")
    # collectstatic args
    all_parser.add_argument("--static-python-executable", type=pathlib.Path, help="Python executable to use for collectstatic")
    all_parser.add_argument("--static-manage-py", type=pathlib.Path, default=__here__/"build"/"assemble"/"manage.py", help="manage.py location for collectstatic")
    all_parser.add_argument("--static-assemble-dir", type=pathlib.Path, default=__here__/"build"/"assemble", help="Where Python is extracted for collectstatic")
    # stage_for_package args
    all_parser.add_argument("--stage-src-root", type=pathlib.Path, default=__here__, help="Source root for staging")
    all_parser.add_argument("--stage-dest-root", type=pathlib.Path, default=__here__/"build"/"assemble", help="Destination root for staging")
    # package args
    all_parser.add_argument("--package-assemble-dir", type=pathlib.Path, default=__here__/"build"/"assemble", help="Directory to package")
    all_parser.add_argument("--package-dist-dir", type=pathlib.Path, default=__here__/"dist", help="Where to put the zip")
    all_parser.add_argument("--package-output", type=pathlib.Path, help="Output zip file name")
    all_parser.set_defaults(func=run_all)

    args = parser.parse_args()
    setup_logging(args.log_level)
    args.func(args)

if __name__ == "__main__":
    main()