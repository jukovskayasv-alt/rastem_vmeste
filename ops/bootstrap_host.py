#!/usr/bin/env python3
"""One-time, owner-invoked bootstrap for the existing SKIF Ubuntu host."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import warnings
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


REPOSITORY = "jukovskayasv-alt/rastem_vmeste"
RUNNER_API = "https://api.github.com/repos/actions/runner/releases/latest"
RUNNER_HOME = Path("/opt/actions-runner")
SKIF_HOME = Path("/opt/skif")
RUNNER_USER = "skifrunner"
MINIMUM_RUNNER = (2, 327, 1)
SHA256 = re.compile(r"[0-9a-f]{64}")
VERSION = re.compile(r"v(\d+)\.(\d+)\.(\d+)")


class BootstrapError(RuntimeError):
    """A bootstrap failure whose message is safe to display."""


@dataclass(frozen=True)
class RunnerAsset:
    tag: str
    name: str
    url: str
    sha256: str


def validate_repository(repository: str) -> str:
    if repository != REPOSITORY:
        raise BootstrapError("repository is not in the deployment allowlist")
    return repository


def select_runner_asset(release: object) -> RunnerAsset:
    if not isinstance(release, dict):
        raise BootstrapError("invalid runner release metadata")
    tag = release.get("tag_name")
    match = VERSION.fullmatch(tag) if isinstance(tag, str) else None
    if match is None or tuple(map(int, match.groups())) < MINIMUM_RUNNER:
        raise BootstrapError("invalid or unsupported runner release tag")
    version = tag.removeprefix("v")
    expected_name = f"actions-runner-linux-x64-{version}.tar.gz"
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise BootstrapError("runner release has no assets")
    matches = [item for item in assets if isinstance(item, dict) and item.get("name") == expected_name]
    if len(matches) != 1:
        raise BootstrapError("exact Linux x64 runner asset was not found")
    item = matches[0]
    expected_url = f"https://github.com/actions/runner/releases/download/{tag}/{expected_name}"
    if item.get("browser_download_url") != expected_url:
        raise BootstrapError("runner asset URL is not official")
    digest = item.get("digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise BootstrapError("runner asset has no sha256 digest")
    sha256 = digest.removeprefix("sha256:")
    if SHA256.fullmatch(sha256) is None:
        raise BootstrapError("runner asset has an invalid sha256 digest")
    return RunnerAsset(tag, expected_name, expected_url, sha256)


def assert_fresh_install(
    runner_home: Path,
    *,
    registration_paths: tuple[Path, ...] | None = None,
) -> None:
    runner_home = Path(runner_home)
    if runner_home.exists() and any(runner_home.iterdir()):
        raise BootstrapError("existing runner installation is not empty; refusing to overwrite")
    paths = registration_paths or (runner_home / ".runner", runner_home / ".credentials")
    if any(Path(path).exists() for path in paths):
        raise BootstrapError("existing runner registration found; refusing to overwrite")


def safe_extract(archive: Path, destination: Path, expected_sha256: str) -> None:
    archive, destination = Path(archive), Path(destination)
    if SHA256.fullmatch(expected_sha256) is None:
        raise BootstrapError("invalid expected checksum")
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise BootstrapError("runner archive checksum mismatch")

    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as bundle:
        members = bundle.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
                raise BootstrapError("runner archive contains an unsafe path or link")
            if not (member.isdir() or member.isfile()):
                raise BootstrapError("runner archive contains an unsupported entry")
        try:
            bundle.extractall(destination, members=members, filter="data")
        except (OSError, tarfile.TarError, ValueError):
            raise BootstrapError("runner archive extraction failed") from None


def _check_host() -> None:
    if os.geteuid() != 0:
        raise BootstrapError("run this installer explicitly as root")
    values: dict[str, str] = {}
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key] = value.strip('"')
    except OSError:
        raise BootstrapError("cannot verify the operating system") from None
    if values.get("ID") != "ubuntu" or values.get("VERSION_ID") != "24.04":
        raise BootstrapError("this installer requires Ubuntu 24.04")
    if os.uname().machine not in {"x86_64", "amd64"}:
        raise BootstrapError("this installer requires x64")


def _fetch_release() -> RunnerAsset:
    request = urllib.request.Request(
        RUNNER_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "skif-bootstrap"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except Exception:
        raise BootstrapError("failed to obtain official runner release metadata") from None
    return select_runner_asset(payload)


def _download(asset: RunnerAsset, target: Path) -> None:
    request = urllib.request.Request(asset.url, headers={"User-Agent": "skif-bootstrap"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, target.open("xb") as output:
            shutil.copyfileobj(response, output)
    except Exception:
        raise BootstrapError("failed to download the official runner archive") from None


def _run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    timeout: float = 120,
) -> None:
    try:
        subprocess.run(
            command,
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            cwd=cwd,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise BootstrapError("host command timed out") from None
    except (OSError, subprocess.CalledProcessError):
        raise BootstrapError(f"host command failed: {command[0]}") from None


def _prepare_host() -> None:
    _run(["apt-get", "update"], timeout=300)
    _run(
        ["apt-get", "install", "-y", "ca-certificates", "git", "docker.io", "docker-buildx"],
        timeout=600,
    )
    _run(["systemctl", "enable", "--now", "docker"])
    try:
        result = subprocess.run(
            ["id", "-u", RUNNER_USER],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        raise BootstrapError("host command timed out") from None
    except OSError:
        raise BootstrapError("host user lookup failed") from None
    if result.returncode != 0:
        _run(["useradd", "--create-home", "--shell", "/bin/bash", RUNNER_USER])
    _run(["usermod", "--append", "--groups", "docker", RUNNER_USER])
    _run(["install", "-d", "-m", "0700", "-o", RUNNER_USER, "-g", RUNNER_USER, str(SKIF_HOME)])
    _run(["install", "-d", "-m", "0750", "-o", RUNNER_USER, "-g", RUNNER_USER, str(RUNNER_HOME)])
    env_file = SKIF_HOME / ".env"
    try:
        descriptor = os.open(env_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        os.close(descriptor)
        shutil.chown(env_file, user=RUNNER_USER, group=RUNNER_USER)


def _read_registration_token() -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            token = getpass.getpass("Временный токен регистрации GitHub Actions: ")
    except (getpass.GetPassWarning, EOFError, KeyboardInterrupt, OSError):
        raise BootstrapError("safe hidden registration-token input is unavailable") from None
    if not token:
        raise BootstrapError("registration token is required")
    return token


def install(repository: str) -> None:
    validate_repository(repository)
    _check_host()
    assert_fresh_install(RUNNER_HOME)
    if not sys.stdin.isatty():
        raise BootstrapError("a terminal is required for hidden registration-token input")
    token = _read_registration_token()
    asset = _fetch_release()

    with tempfile.TemporaryDirectory(prefix="skif-runner-") as temporary:
        archive = Path(temporary) / asset.name
        staging = Path(temporary) / "extracted"
        _download(asset, archive)
        safe_extract(archive, staging, asset.sha256)
        _prepare_host()
        assert_fresh_install(RUNNER_HOME)
        for child in staging.iterdir():
            shutil.move(str(child), RUNNER_HOME / child.name)

    shutil.chown(RUNNER_HOME, user=RUNNER_USER, group=RUNNER_USER)
    for path in RUNNER_HOME.rglob("*"):
        shutil.chown(path, user=RUNNER_USER, group=RUNNER_USER)

    _run(
        [str(RUNNER_HOME / "bin" / "installdependencies.sh")],
        cwd=RUNNER_HOME,
        timeout=600,
    )
    environment = os.environ.copy()
    environment["ACTIONS_RUNNER_INPUT_TOKEN"] = token
    try:
        _run(
            [
                "runuser", "-u", RUNNER_USER, "--", "./config.sh",
                "--unattended", "--url", f"https://github.com/{REPOSITORY}",
                "--name", "skif", "--labels", "skif", "--work", "_work",
            ],
            env=environment,
            cwd=RUNNER_HOME,
        )
    finally:
        environment.pop("ACTIONS_RUNNER_INPUT_TOKEN", None)
        token = ""
    _run([str(RUNNER_HOME / "svc.sh"), "install", RUNNER_USER], cwd=RUNNER_HOME)
    _run([str(RUNNER_HOME / "svc.sh"), "start"], cwd=RUNNER_HOME)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="must be the fixed private repository owner/name")
    arguments = parser.parse_args(argv)
    try:
        install(arguments.repository)
    except BootstrapError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
    print("Runner установлен. Перед первым deploy заполните /opt/skif/.env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
