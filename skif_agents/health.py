from __future__ import annotations

import json
import os
import tempfile
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from .core import ROLES


async def validate_telegrams(telegrams):
    identities = set()
    for role, telegram in telegrams.items():
        try:
            me = await asyncio.to_thread(telegram.call, "getMe")
            hook = await asyncio.to_thread(telegram.call, "getWebhookInfo")
        except Exception:
            raise ValueError(f"{role}: не удалось проверить Telegram") from None
        if hook.get("url"):
            raise ValueError(
                f"{role}: уже настроен webhook. Остановите старое приложение перед long polling; "
                "автоматического удаления webhook нет."
            )
        identity = me.get("id")
        if identity in identities:
            raise ValueError("Для каждой роли нужен отдельный Telegram-бот")
        identities.add(identity)


def _utc(value: datetime | None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def write_heartbeat(path, release, roles, timestamp=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "release": release,
        "roles": list(roles),
        "timestamp": _utc(timestamp).isoformat(),
    }
    handle, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def check_heartbeat(path, release, timestamp=None) -> bool:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        written = datetime.fromisoformat(payload["timestamp"])
        age = (_utc(timestamp) - _utc(written)).total_seconds()
        return bool(
            release
            and payload["release"]
            and payload["release"] == release
            and set(payload["roles"]) == set(ROLES)
            and 0 <= age < 60
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False
