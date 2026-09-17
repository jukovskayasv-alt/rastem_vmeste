from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops.deploy import DeploymentError, DockerEngine, RunningDeployment, deploy


OLD_ID = "sha256:" + "a" * 64
OLD_RELEASE = "1" * 40
NEW_RELEASE = "2" * 40


class MemoryEngine:
    """Stateful substitute for the external Docker daemon."""

    def __init__(self, running=None, *, fail=None, readiness=(True,)):
        self.running = running
        self.fail = fail
        self.readiness = iter(readiness)
        self.calls = []

    def build(self, source, image):
        self.calls.append(("build", image))
        if self.fail == "build":
            raise RuntimeError("secret build detail")

    def preflight(self, image, revision, source, home):
        self.calls.append(("preflight", image))
        if self.fail == "preflight":
            raise RuntimeError("TOKEN=secret")

    def current(self):
        self.calls.append(("current",))
        return self.running

    def stop(self):
        self.calls.append(("stop",))
        self.running = None

    def start(self, image, revision, source, home):
        self.calls.append(("start", image, revision))
        if self.running is not None:
            raise AssertionError("overlapping instances")
        if self.fail == "start" and image != OLD_ID:
            raise RuntimeError("start secret")
        self.running = RunningDeployment(image, revision, 100.0)
        return 100.0

    def ready(self, revision, started_at, timeout):
        self.calls.append(("ready", revision, started_at, timeout))
        return next(self.readiness, False)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.source = self.home / "source"
        self.source.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_success_replaces_instance_and_writes_durable_receipt(self):
        engine = MemoryEngine(RunningDeployment(OLD_ID, OLD_RELEASE, 1.0))

        receipt = deploy(engine, self.source, NEW_RELEASE, self.home, timeout=1)

        expected_image = f"skif-bots:{NEW_RELEASE}"
        self.assertEqual(engine.running.image, expected_image)
        self.assertLess(engine.calls.index(("preflight", expected_image)), engine.calls.index(("stop",)))
        stored = json.loads((self.home / "deployments" / "current.json").read_text())
        self.assertEqual(stored, receipt)
        self.assertEqual(stored["revision"], NEW_RELEASE)
        self.assertEqual(stored["image"], expected_image)
        self.assertNotIn("secret", json.dumps(stored).lower())

    def test_build_and_preflight_fail_before_current_instance_is_stopped(self):
        for stage in ("build", "preflight"):
            with self.subTest(stage=stage):
                engine = MemoryEngine(RunningDeployment(OLD_ID, OLD_RELEASE, 1.0), fail=stage)
                with self.assertRaisesRegex(DeploymentError, f"^{stage} failed$") as caught:
                    deploy(engine, self.source, NEW_RELEASE, self.home, timeout=0)
                self.assertEqual(engine.running.image, OLD_ID)
                self.assertNotIn("stop", [call[0] for call in engine.calls])
                self.assertNotIn("secret", str(caught.exception).lower())

    def test_failed_readiness_restores_previous_immutable_image_id(self):
        engine = MemoryEngine(
            RunningDeployment(OLD_ID, OLD_RELEASE, 1.0), readiness=(False, True)
        )

        with self.assertRaisesRegex(DeploymentError, "readiness failed; previous release restored"):
            deploy(engine, self.source, NEW_RELEASE, self.home, timeout=0)

        self.assertEqual(engine.running.image, OLD_ID)
        starts = [call for call in engine.calls if call[0] == "start"]
        self.assertEqual(starts[-1], ("start", OLD_ID, OLD_RELEASE))
        self.assertFalse((self.home / "deployments" / "current.json").exists())

    def test_first_install_start_failure_leaves_no_container(self):
        engine = MemoryEngine(fail="start")
        with self.assertRaisesRegex(DeploymentError, "start failed"):
            deploy(engine, self.source, NEW_RELEASE, self.home, timeout=0)
        self.assertIsNone(engine.running)

    def test_receipt_failure_restores_previous_container_and_receipt(self):
        receipt = self.home / "deployments" / "current.json"
        receipt.parent.mkdir()
        receipt.write_text('{"revision":"old"}\n')
        engine = MemoryEngine(
            RunningDeployment(OLD_ID, OLD_RELEASE, 1.0), readiness=(True, True)
        )

        def failed_receipt(home, revision, image):
            receipt.write_text('{"revision":"new"}\n')
            raise OSError("disk secret")

        with patch("ops.deploy._write_receipt", side_effect=failed_receipt):
            with self.assertRaisesRegex(
                DeploymentError, "receipt write failed; previous release restored"
            ):
                deploy(engine, self.source, NEW_RELEASE, self.home, timeout=1)

        self.assertEqual(engine.running.image, OLD_ID)
        self.assertEqual(receipt.read_text(), '{"revision":"old"}\n')

    def test_receipt_restoration_failure_is_reported_separately(self):
        receipt = self.home / "deployments" / "current.json"
        receipt.parent.mkdir()
        receipt.write_text('{"revision":"old"}\n')
        engine = MemoryEngine(
            RunningDeployment(OLD_ID, OLD_RELEASE, 1.0), readiness=(True, True)
        )
        with (
            patch("ops.deploy._write_receipt", side_effect=OSError("write secret")),
            patch("ops.deploy._restore_receipt", side_effect=OSError("restore secret")),
        ):
            with self.assertRaisesRegex(
                DeploymentError,
                "receipt write failed; previous release restored; receipt restoration failed",
            ) as caught:
                deploy(engine, self.source, NEW_RELEASE, self.home, timeout=1)
        self.assertNotIn("secret", str(caught.exception))
        self.assertEqual(engine.running.image, OLD_ID)

    def test_receipt_restoration_failure_is_retained_when_container_rollback_fails(self):
        engine = MemoryEngine(
            RunningDeployment(OLD_ID, OLD_RELEASE, 1.0), readiness=(True, False)
        )
        with (
            patch("ops.deploy._write_receipt", side_effect=OSError("write secret")),
            patch("ops.deploy._restore_receipt", side_effect=OSError("restore secret")),
        ):
            with self.assertRaisesRegex(
                DeploymentError,
                "receipt write failed; rollback failed; receipt restoration failed",
            ):
                deploy(engine, self.source, NEW_RELEASE, self.home, timeout=0)

    def test_first_install_receipt_failure_durably_removes_candidate_and_receipt(self):
        engine = MemoryEngine(readiness=(True,))
        real_fsync = os.fsync
        directory_syncs = 0

        def fail_first_directory_sync(descriptor):
            nonlocal directory_syncs
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                directory_syncs += 1
                if directory_syncs == 1:
                    raise OSError("directory sync secret")
            return real_fsync(descriptor)

        with patch("ops.deploy.os.fsync", side_effect=fail_first_directory_sync):
            with self.assertRaisesRegex(DeploymentError, "^receipt write failed$") as caught:
                deploy(engine, self.source, NEW_RELEASE, self.home, timeout=1)

        self.assertIsNone(engine.running)
        self.assertFalse((self.home / "deployments" / "current.json").exists())
        self.assertEqual(directory_syncs, 2)
        self.assertNotIn("secret", str(caught.exception))

    def test_invalid_revision_is_rejected_without_engine_calls(self):
        engine = MemoryEngine()
        with self.assertRaisesRegex(ValueError, "40 lowercase hexadecimal"):
            deploy(engine, self.source, "main", self.home)
        self.assertEqual(engine.calls, [])

    def test_held_lock_rejects_concurrent_deployment(self):
        import fcntl

        lock = self.home / ".deploy.lock"
        with lock.open("w") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(DeploymentError, "deployment already in progress"):
                deploy(MemoryEngine(), self.source, NEW_RELEASE, self.home)


class DockerEngineTests(unittest.TestCase):
    def test_current_returns_image_id_and_release(self):
        result = subprocess.CompletedProcess(
            [], 0, stdout=OLD_ID + "\nSKIF_RELEASE=" + OLD_RELEASE + "\n", stderr=""
        )
        with patch("ops.deploy.subprocess.run", return_value=result) as run:
            current = DockerEngine().current()
        self.assertEqual(current.image, OLD_ID)
        self.assertEqual(current.release, OLD_RELEASE)
        self.assertIn("inspect", run.call_args.args[0])

    def test_current_only_treats_no_such_container_as_absent(self):
        missing = subprocess.CompletedProcess([], 1, stdout="", stderr="No such container: skif-bots")
        daemon_error = subprocess.CompletedProcess([], 1, stdout="", stderr="daemon unavailable TOKEN=x")
        with patch("ops.deploy.subprocess.run", return_value=missing):
            self.assertIsNone(DockerEngine().current())
        with patch("ops.deploy.subprocess.run", return_value=daemon_error):
            with self.assertRaises(subprocess.CalledProcessError):
                DockerEngine().current()

    def test_ready_requires_heartbeat_newer_than_container_start(self):
        responses = [
            subprocess.CompletedProcess([], 0, stdout="99\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="101\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        ]
        with patch("ops.deploy.subprocess.run", side_effect=responses) as run:
            engine = DockerEngine()
            self.assertFalse(engine.ready(NEW_RELEASE, 100.0, 4.0))
            self.assertTrue(engine.ready(NEW_RELEASE, 100.0, 4.0))
        health = run.call_args_list[-1].args[0]
        self.assertEqual(health[-5:], ["python", "-m", "skif_agents", "health", "--root=/app"])

    def test_start_uses_fixed_container_volume_and_release(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "src"
            home = Path(root) / "home"
            (source / "data").mkdir(parents=True)
            home.mkdir()
            responses = [
                subprocess.CompletedProcess([], 0, stdout="", stderr=""),
                subprocess.CompletedProcess([], 0, stdout="2026-09-17T12:00:00Z\n", stderr=""),
            ]
            with patch("ops.deploy.subprocess.run", side_effect=responses) as run:
                DockerEngine().start(f"skif-bots:{NEW_RELEASE}", NEW_RELEASE, source, home)
        command = run.call_args_list[0].args[0]
        self.assertIn("skif-bots", command)
        self.assertIn("skif_runtime:/app/runtime", command)
        self.assertIn(f"SKIF_RELEASE={NEW_RELEASE}", command)
        self.assertNotIn(f"{source / 'data'}:/app/data:ro", command)

    def test_preflight_uses_immutable_image_data(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "src"
            home = Path(root) / "home"
            with patch("ops.deploy.subprocess.run") as run:
                DockerEngine().preflight(f"skif-bots:{NEW_RELEASE}", NEW_RELEASE, source, home)
        for call in run.call_args_list:
            command = call.args[0]
            self.assertFalse(any("/app/data" in item for item in command), command)

    def test_every_docker_command_has_a_finite_timeout(self):
        responses = [
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            subprocess.CompletedProcess([], 0, stdout=OLD_ID + "\nSKIF_RELEASE=" + OLD_RELEASE, stderr=""),
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="101\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        ]
        with patch("ops.deploy.subprocess.run", side_effect=responses) as run:
            engine = DockerEngine()
            engine.build(Path("src"), f"skif-bots:{NEW_RELEASE}")
            engine.preflight(f"skif-bots:{NEW_RELEASE}", NEW_RELEASE, Path("src"), Path("home"))
            engine.current()
            engine.stop()
            engine.ready(NEW_RELEASE, 100.0, 3.0)
        self.assertTrue(all(call.kwargs.get("timeout", 0) > 0 for call in run.call_args_list))
        self.assertLessEqual(run.call_args_list[-1].kwargs["timeout"], 3.0)

    def test_real_adapter_stops_candidate_before_restoring_prior_image_id(self):
        commands = []
        inspect_count = 0
        stat_count = 0

        def docker(command, **kwargs):
            nonlocal inspect_count, stat_count
            commands.append(command)
            if command[1] == "inspect":
                inspect_count += 1
                if inspect_count == 1:
                    output = OLD_ID + "\nSKIF_RELEASE=" + OLD_RELEASE + "\n"
                else:
                    output = "2026-09-17T12:00:00Z\n"
                return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")
            if "stat" in command:
                stat_count += 1
                if stat_count == 1:
                    raise subprocess.TimeoutExpired(command, kwargs["timeout"])
                output = "2000000000\n"
                return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as root, patch("ops.deploy.subprocess.run", side_effect=docker):
            with self.assertRaisesRegex(DeploymentError, "previous release restored"):
                deploy(DockerEngine(), Path(root) / "src", NEW_RELEASE, Path(root) / "home", timeout=0)

        candidate = next(i for i, cmd in enumerate(commands) if "--detach" in cmd and cmd[-1] == f"skif-bots:{NEW_RELEASE}")
        restore = next(i for i, cmd in enumerate(commands) if "--detach" in cmd and cmd[-1] == OLD_ID)
        removal = max(i for i, cmd in enumerate(commands[:restore]) if cmd[1:3] == ["rm", "--force"])
        self.assertLess(candidate, removal)
        self.assertLess(removal, restore)


if __name__ == "__main__":
    unittest.main()
