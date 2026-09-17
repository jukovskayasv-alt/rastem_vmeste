from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from skif_agents.core import ROLES
from skif_agents.health import check_heartbeat, write_heartbeat
from skif_agents.health import validate_telegrams


class FakeTelegram:
    def __init__(self, ident, webhook=""):
        self.ident = ident
        self.webhook = webhook
        self.calls = []

    def call(self, method):
        self.calls.append(method)
        if method == "getMe":
            return {"id": self.ident}
        if method == "getWebhookInfo":
            return {"url": self.webhook}
        raise AssertionError(f"unexpected Telegram method: {method}")


class HeartbeatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "runtime" / "health.json"
        self.now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)

    def test_matching_fresh_four_role_heartbeat_is_healthy(self):
        write_heartbeat(self.path, "release-7", ROLES, timestamp=self.now)

        self.assertTrue(check_heartbeat(self.path, "release-7", timestamp=self.now))
        self.assertEqual(set(json.loads(self.path.read_text())["roles"]), set(ROLES))

    def test_heartbeat_at_sixty_seconds_is_stale(self):
        write_heartbeat(
            self.path, "release-7", ROLES, timestamp=self.now - timedelta(seconds=60)
        )

        self.assertFalse(check_heartbeat(self.path, "release-7", timestamp=self.now))

    def test_wrong_release_is_unhealthy(self):
        write_heartbeat(self.path, "release-6", ROLES, timestamp=self.now)

        self.assertFalse(check_heartbeat(self.path, "release-7", timestamp=self.now))

    def test_empty_release_is_unhealthy(self):
        write_heartbeat(self.path, "", ROLES, timestamp=self.now)

        self.assertFalse(check_heartbeat(self.path, "", timestamp=self.now))

    def test_missing_role_is_unhealthy(self):
        write_heartbeat(self.path, "release-7", ROLES[:-1], timestamp=self.now)

        self.assertFalse(check_heartbeat(self.path, "release-7", timestamp=self.now))

    def test_missing_or_invalid_file_is_unhealthy(self):
        self.assertFalse(check_heartbeat(self.path, "release-7", timestamp=self.now))
        self.path.parent.mkdir(parents=True)
        self.path.write_text("not JSON")
        self.assertFalse(check_heartbeat(self.path, "release-7", timestamp=self.now))


class TelegramValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_validation_only_checks_identity_and_webhook(self):
        telegrams = {role: FakeTelegram(index) for index, role in enumerate(ROLES)}

        await validate_telegrams(telegrams)

        for telegram in telegrams.values():
            self.assertEqual(telegram.calls, ["getMe", "getWebhookInfo"])

    async def test_validation_rejects_duplicate_identity_without_secret_details(self):
        telegrams = {role: FakeTelegram(1) for role in ROLES}

        with self.assertRaisesRegex(ValueError, "отдельный Telegram-бот") as caught:
            await validate_telegrams(telegrams)

        self.assertNotIn("token", str(caught.exception).casefold())

if __name__ == "__main__":
    unittest.main()
