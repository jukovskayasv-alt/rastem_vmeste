from __future__ import annotations

import hashlib
import io
import subprocess
import tarfile
import tempfile
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ops.bootstrap_host import (
    BootstrapError,
    assert_fresh_install,
    safe_extract,
    select_runner_asset,
    validate_repository,
)


class BootstrapValidationTests(unittest.TestCase):
    def test_repository_allowlist_accepts_only_production_repository(self):
        self.assertEqual(
            validate_repository("jukovskayasv-alt/rastem_vmeste"),
            "jukovskayasv-alt/rastem_vmeste",
        )
        for value in (
            "jukovskayasv-alt/skif-bots",
            "other/rastem_vmeste",
            "jukovskayasv-alt/rastem_vmeste.git",
            "jukovskayasv-alt/rastem_vmeste/extra",
            "https://github.com/jukovskayasv-alt/rastem_vmeste",
        ):
            with self.subTest(value=value), self.assertRaises(BootstrapError):
                validate_repository(value)

    def test_workflow_deploys_only_private_skif_branch_of_production_repository(self):
        workflow = (
            Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("  push:\n    branches:\n      - skif\n", workflow)
        deploy_gate = next(
            line.strip() for line in workflow.splitlines() if line.strip().startswith("if:")
        )
        self.assertIn("github.event.repository.private == true", deploy_gate)
        self.assertIn("github.repository == 'jukovskayasv-alt/rastem_vmeste'", deploy_gate)
        self.assertIn("github.ref == 'refs/heads/skif'", deploy_gate)
        self.assertIn("github.event_name == 'push'", deploy_gate)
        self.assertNotIn("jukovskayasv-alt/skif-bots", workflow)
        self.assertNotIn("refs/heads/main", workflow)

    def test_runner_asset_requires_exact_linux_x64_identity_and_sha256(self):
        digest = "a" * 64
        release = {
            "tag_name": "v2.337.0",
            "assets": [{
                "name": "actions-runner-linux-x64-2.337.0.tar.gz",
                "browser_download_url": (
                    "https://github.com/actions/runner/releases/download/"
                    "v2.337.0/actions-runner-linux-x64-2.337.0.tar.gz"
                ),
                "digest": f"sha256:{digest}",
            }],
        }
        asset = select_runner_asset(release)
        self.assertEqual(asset.sha256, digest)

        bad_cases = [
            {**release, "tag_name": "2.337.0"},
            {**release, "assets": [{**release["assets"][0], "name": "actions-runner-linux-arm64-2.337.0.tar.gz"}]},
            {**release, "assets": [{**release["assets"][0], "digest": None}]},
            {**release, "assets": [{**release["assets"][0], "digest": "sha256:" + "A" * 64}]},
            {**release, "assets": [{**release["assets"][0], "browser_download_url": "https://example.invalid/runner.tgz"}]},
        ]
        for bad in bad_cases:
            with self.subTest(release=bad), self.assertRaises(BootstrapError):
                select_runner_asset(bad)

    def test_archive_digest_is_checked_before_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "runner.tar.gz"
            destination = Path(temporary) / "runner"
            with tarfile.open(archive, "w:gz") as bundle:
                data = b"runner"
                item = tarfile.TarInfo("bin/Runner.Listener")
                item.size = len(data)
                bundle.addfile(item, io.BytesIO(data))

            safe_extract(archive, destination, hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertEqual((destination / "bin" / "Runner.Listener").read_bytes(), b"runner")

            with self.assertRaisesRegex(BootstrapError, "checksum"):
                safe_extract(archive, Path(temporary) / "bad", "0" * 64)

    def test_archive_rejects_traversal_and_unsafe_links(self):
        for kind, name, linkname in (
            ("file", "../escape", ""),
            ("symlink", "link", "../../escape"),
            ("hardlink", "hard", "/etc/passwd"),
        ):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                archive = Path(temporary) / "unsafe.tar"
                with tarfile.open(archive, "w") as bundle:
                    item = tarfile.TarInfo(name)
                    if kind == "symlink":
                        item.type, item.linkname = tarfile.SYMTYPE, linkname
                    elif kind == "hardlink":
                        item.type, item.linkname = tarfile.LNKTYPE, linkname
                    else:
                        item.size = 0
                    bundle.addfile(item, io.BytesIO(b"") if kind == "file" else None)
                digest = hashlib.sha256(archive.read_bytes()).hexdigest()
                with self.assertRaises(BootstrapError):
                    safe_extract(archive, Path(temporary) / "out", digest)
                self.assertFalse((Path(temporary) / "escape").exists())

    def test_rerun_refuses_nonempty_runner_or_existing_registration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = root / "runner"
            runner.mkdir()
            assert_fresh_install(runner)

            (runner / "keep.txt").write_text("existing", encoding="utf-8")
            with self.assertRaisesRegex(BootstrapError, "existing runner"):
                assert_fresh_install(runner)
            self.assertEqual((runner / "keep.txt").read_text(encoding="utf-8"), "existing")

            empty = root / "empty"
            empty.mkdir()
            (root / ".runner").write_text("registered", encoding="utf-8")
            with self.assertRaisesRegex(BootstrapError, "registration"):
                assert_fresh_install(empty, registration_paths=(root / ".runner",))


class BootstrapInstallTests(unittest.TestCase):
    def test_subprocess_timeouts_are_redacted(self):
        from ops.bootstrap_host import _prepare_host, _run

        secret = "never-log-this-secret"
        expired = subprocess.TimeoutExpired(["command", "--token", secret], 1)
        with patch("ops.bootstrap_host.subprocess.run", side_effect=expired):
            with self.assertRaises(BootstrapError) as caught:
                _run(["command", "--token", secret], env={"TOKEN": secret})
        self.assertNotIn(secret, str(caught.exception))
        self.assertNotIn("--token", str(caught.exception))

        def run_until_id(command, **_kwargs):
            if command[:2] == ["id", "-u"]:
                raise subprocess.TimeoutExpired(command, 10)
            return SimpleNamespace(returncode=0)

        with (
            patch("ops.bootstrap_host._run"),
            patch("ops.bootstrap_host.subprocess.run", side_effect=run_until_id),
        ):
            with self.assertRaises(BootstrapError) as caught:
                _prepare_host()
        self.assertNotIn("id", str(caught.exception))
        self.assertNotIn("skifrunner", str(caught.exception))

    def test_unsafe_or_interrupted_token_input_aborts_before_mutation(self):
        def insecure_getpass(_prompt):
            warnings.warn("fallback", getpass.GetPassWarning)
            return "visible-token"

        import getpass

        for failure in (insecure_getpass, EOFError(), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):
                with (
                    patch("ops.bootstrap_host._check_host"),
                    patch("ops.bootstrap_host.assert_fresh_install"),
                    patch("ops.bootstrap_host.sys.stdin.isatty", return_value=True),
                    patch("ops.bootstrap_host.getpass.getpass", side_effect=failure),
                    patch("ops.bootstrap_host._fetch_release") as fetch,
                    patch("ops.bootstrap_host._prepare_host") as mutate,
                ):
                    with self.assertRaisesRegex(BootstrapError, "hidden"):
                        from ops.bootstrap_host import install
                        install("jukovskayasv-alt/rastem_vmeste")
                    fetch.assert_not_called()
                    mutate.assert_not_called()

    def test_install_uses_environment_token_and_orders_dependencies_before_service(self):
        from ops.bootstrap_host import RunnerAsset, install

        calls = []
        secret = "temporary-secret-value"
        registration_environment = {"PATH": "/usr/bin"}

        def record(command, **kwargs):
            if kwargs.get("env") is not None:
                kwargs["env"] = kwargs["env"].copy()
            calls.append((list(command), kwargs))

        def fake_extract(_archive, destination, _digest):
            destination.mkdir(parents=True)
            (destination / "bin").mkdir()
            for relative in ("bin/installdependencies.sh", "config.sh", "svc.sh"):
                (destination / relative).write_text("#!/bin/sh\n", encoding="utf-8")

        asset = RunnerAsset("v2.337.0", "runner.tar.gz", "https://example.invalid", "a" * 64)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner_home, skif_home = root / "runner", root / "skif"
            runner_home.mkdir()
            skif_home.mkdir()
            with (
                patch("ops.bootstrap_host.RUNNER_HOME", runner_home),
                patch("ops.bootstrap_host.SKIF_HOME", skif_home),
                patch("ops.bootstrap_host._check_host"),
                patch("ops.bootstrap_host.sys.stdin.isatty", return_value=True),
                patch("ops.bootstrap_host.getpass.getpass", return_value=secret),
                patch("ops.bootstrap_host._fetch_release", return_value=asset),
                patch("ops.bootstrap_host._download"),
                patch("ops.bootstrap_host.safe_extract", side_effect=fake_extract),
                patch("ops.bootstrap_host._run", side_effect=record),
                patch("ops.bootstrap_host.subprocess.run", return_value=SimpleNamespace(returncode=1)),
                patch("ops.bootstrap_host.shutil.chown"),
                patch("ops.bootstrap_host.os.environ.copy", return_value=registration_environment),
            ):
                install("jukovskayasv-alt/rastem_vmeste")

        commands = [command for command, _kwargs in calls]
        flat = [part for command in commands for part in command]
        self.assertNotIn(secret, flat)
        install_packages = next(command for command in commands if command[:3] == ["apt-get", "install", "-y"])
        self.assertEqual(
            install_packages[3:],
            ["ca-certificates", "git", "docker.io", "docker-buildx"],
        )
        docker_service = ["systemctl", "enable", "--now", "docker"]
        dependencies = [str(runner_home / "bin" / "installdependencies.sh")]
        config_index = next(index for index, command in enumerate(commands) if "./config.sh" in command)
        self.assertLess(commands.index(docker_service), commands.index(dependencies))
        self.assertLess(commands.index(dependencies), config_index)
        self.assertLess(config_index, next(index for index, command in enumerate(commands) if "install" in command and "svc.sh" in command[0]))

        config_command, config_kwargs = calls[config_index]
        self.assertNotIn("--token", config_command)
        self.assertEqual(config_kwargs["env"]["ACTIONS_RUNNER_INPUT_TOKEN"], secret)
        self.assertNotIn("RUNNER_REGISTRATION_TOKEN", config_kwargs["env"])
        self.assertNotIn("ACTIONS_RUNNER_INPUT_TOKEN", registration_environment)


if __name__ == "__main__":
    unittest.main()
