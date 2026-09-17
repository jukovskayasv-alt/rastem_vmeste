from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


CONTAINER = "skif-bots"
VOLUME = "skif_runtime"
REVISION = re.compile(r"[0-9a-f]{40}")


class DeploymentError(RuntimeError):
    """A deployment failure safe to display in CI logs."""


@dataclass(frozen=True)
class RunningDeployment:
    image: str
    release: str
    started_at: float


def _run(command, *, timeout: float):
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class DockerEngine:
    """Small adapter around the Docker CLI; transaction policy lives in deploy()."""

    def build(self, source: Path, image: str) -> None:
        _run(["docker", "build", "--pull", "--tag", image, str(source)], timeout=600)

    def preflight(self, image: str, revision: str, source: Path, home: Path) -> None:
        base = [
            "docker", "run", "--rm", "--env-file", str(home / ".env"),
            "--env", f"SKIF_RELEASE={revision}",
            "--volume", f"{VOLUME}:/app/runtime",
            image, "python", "-m", "skif_agents",
        ]
        _run(base + ["check", "--root=/app"], timeout=30)
        _run(base + ["probe", "--root=/app"], timeout=30)

    def current(self) -> RunningDeployment | None:
        result = subprocess.run(
            [
                "docker", "inspect", "--format",
                "{{.Image}}\n{{range .Config.Env}}{{println .}}{{end}}",
                CONTAINER,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            if "No such container" in result.stderr or "No such object" in result.stderr:
                return None
            raise subprocess.CalledProcessError(
                result.returncode, result.args, output=result.stdout, stderr=result.stderr
            )
        lines = result.stdout.splitlines()
        if not lines or not lines[0].startswith("sha256:"):
            raise RuntimeError("invalid container inspection")
        release = next(
            (line.removeprefix("SKIF_RELEASE=") for line in lines[1:] if line.startswith("SKIF_RELEASE=")),
            "",
        )
        return RunningDeployment(lines[0], release, 0.0)

    def stop(self) -> None:
        result = subprocess.run(
            ["docker", "rm", "--force", CONTAINER],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0 and "No such container" not in result.stderr:
            raise subprocess.CalledProcessError(result.returncode, result.args)

    def start(self, image: str, revision: str, source: Path, home: Path) -> float:
        _run([
            "docker", "run", "--detach", "--name", CONTAINER,
            "--restart", "unless-stopped",
            "--env-file", str(home / ".env"),
            "--env", f"SKIF_RELEASE={revision}",
            "--volume", f"{VOLUME}:/app/runtime",
            "--security-opt", "no-new-privileges:true",
            "--cap-drop", "ALL", image,
        ], timeout=60)
        result = _run(
            ["docker", "inspect", "--format", "{{.State.StartedAt}}", CONTAINER],
            timeout=15,
        )
        value = result.stdout.strip().replace("Z", "+00:00")
        return datetime.fromisoformat(value).timestamp()

    def ready(self, revision: str, started_at: float, timeout: float) -> bool:
        deadline = time.monotonic() + max(0.001, timeout)
        command_timeout = max(0.001, min(10.0, deadline - time.monotonic()))
        stat = subprocess.run(
            ["docker", "exec", CONTAINER, "stat", "-c", "%Y", "/app/runtime/health.json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=command_timeout,
        )
        try:
            heartbeat_time = float(stat.stdout.strip())
        except ValueError:
            return False
        if stat.returncode != 0 or heartbeat_time < started_at:
            return False
        command_timeout = max(0.001, min(10.0, deadline - time.monotonic()))
        health = subprocess.run(
            [
                "docker", "exec", "--env", f"SKIF_RELEASE={revision}", CONTAINER,
                "python", "-m", "skif_agents", "health", "--root=/app",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=command_timeout,
        )
        return health.returncode == 0


def _wait_ready(engine, revision: str, started_at: float, timeout: int) -> bool:
    deadline = time.monotonic() + max(0, timeout)
    while True:
        remaining = max(0.001, deadline - time.monotonic())
        if engine.ready(revision, started_at, remaining):
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.5, remaining))


def _write_receipt(home: Path, revision: str, image: str) -> dict:
    directory = home / "deployments"
    directory.mkdir(parents=True, exist_ok=True)
    receipt = {
        "revision": revision,
        "image": image,
        "deployed_at": datetime.now(timezone.utc).isoformat(),
    }
    descriptor, temporary = tempfile.mkstemp(prefix="current.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(receipt, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, directory / "current.json")
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return receipt


def _restore_receipt(path: Path, previous: bytes | None) -> None:
    if previous is None:
        try:
            path.unlink()
        except FileNotFoundError:
            return
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="current.restore.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(previous)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def deploy(engine, source: Path, revision: str, home: Path, timeout: int = 90) -> dict:
    """Deploy one immutable revision, restoring the prior image if activation fails."""
    if REVISION.fullmatch(revision) is None:
        raise ValueError("revision must be 40 lowercase hexadecimal characters")
    if timeout < 0:
        raise ValueError("timeout must be non-negative")
    source, home = Path(source), Path(home)
    home.mkdir(parents=True, exist_ok=True)
    image = f"skif-bots:{revision}"

    with (home / ".deploy.lock").open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DeploymentError("deployment already in progress") from None

        try:
            engine.build(source, image)
        except Exception:
            raise DeploymentError("build failed") from None
        try:
            engine.preflight(image, revision, source, home)
        except Exception:
            raise DeploymentError("preflight failed") from None
        try:
            previous = engine.current()
        except Exception:
            raise DeploymentError("current deployment inspection failed") from None

        receipt_path = home / "deployments" / "current.json"
        try:
            previous_receipt = receipt_path.read_bytes()
        except FileNotFoundError:
            previous_receipt = None
        except OSError:
            raise DeploymentError("current receipt read failed") from None

        try:
            engine.stop()
        except Exception:
            raise DeploymentError("stop failed") from None

        failure = "start failed"
        try:
            started_at = engine.start(image, revision, source, home)
            failure = "readiness failed"
            if not _wait_ready(engine, revision, started_at, timeout):
                raise RuntimeError("candidate did not become ready")
            failure = "receipt write failed"
            receipt = _write_receipt(home, revision, image)
        except Exception:
            rollback_failed = False
            try:
                engine.stop()
                if previous is not None:
                    restored_at = engine.start(previous.image, previous.release, source, home)
                    if not _wait_ready(engine, previous.release, restored_at, timeout):
                        raise RuntimeError("restored instance did not become ready")
            except Exception:
                rollback_failed = True
            receipt_restore_failed = False
            if failure == "receipt write failed":
                try:
                    _restore_receipt(receipt_path, previous_receipt)
                except Exception:
                    receipt_restore_failed = True
            if rollback_failed:
                suffix = "; rollback failed"
                if receipt_restore_failed:
                    suffix += "; receipt restoration failed"
                raise DeploymentError(failure + suffix) from None
            suffix = "; previous release restored" if previous is not None else ""
            if receipt_restore_failed:
                suffix += "; receipt restoration failed"
            raise DeploymentError(failure + suffix) from None
        return receipt
