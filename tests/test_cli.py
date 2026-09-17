from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from skif_agents.core import ROLES
from skif_agents.health import write_heartbeat


class CLITests(unittest.TestCase):
    def test_check_with_empty_environment_exits_two(self):
        with tempfile.TemporaryDirectory() as root:
            result = subprocess.run(
                [sys.executable, "-m", "skif_agents", "check", "--root", root],
                cwd=".",
                env={},
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("Требуются настройки", result.stderr)

    def test_health_uses_release_and_configured_root(self):
        with tempfile.TemporaryDirectory() as root:
            write_heartbeat(
                Path(root) / "runtime" / "health.json",
                "release-7",
                ROLES,
                timestamp=datetime.now(timezone.utc),
            )
            result = subprocess.run(
                [sys.executable, "-m", "skif_agents", "health", "--root", root],
                cwd=".",
                env={"SKIF_RELEASE": "release-7"},
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_health_rejects_unversioned_heartbeat(self):
        with tempfile.TemporaryDirectory() as root:
            write_heartbeat(
                Path(root) / "runtime" / "health.json",
                "",
                ROLES,
                timestamp=datetime.now(timezone.utc),
            )
            result = subprocess.run(
                [sys.executable, "-m", "skif_agents", "health", "--root", root],
                cwd=".",
                env={},
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Нет свежего heartbeat", result.stderr)


if __name__ == "__main__":
    unittest.main()
