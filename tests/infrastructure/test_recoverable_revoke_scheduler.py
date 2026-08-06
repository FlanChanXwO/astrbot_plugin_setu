from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot_plugin_setu.src.infrastructure.sending.revoke_scheduler import (
    RecoverableRevokeScheduler,
)


class _Bot:
    def __init__(
        self, group_file_responses: list[object], *, delete_fails: bool = False
    ) -> None:
        self._group_file_responses = iter(group_file_responses)
        self._delete_fails = delete_fails
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_action(self, action: str, **kwargs: object) -> object:
        self.calls.append((action, kwargs))
        if action == "get_group_root_files":
            return next(self._group_file_responses)
        if action in {"delete_group_file", "delete_msg"}:
            if self._delete_fails:
                raise RuntimeError("模拟删除失败")
            return {"status": "ok"}
        raise AssertionError(f"unexpected action: {action}")


class _Event:
    def __init__(self, bot: _Bot) -> None:
        self.bot = bot
        self.platform = SimpleNamespace(name="napcat")

    def get_group_id(self) -> str:
        return "10001"

    def get_platform_id(self) -> str:
        return "onebot-main"


class _Platform:
    def __init__(self, bot: _Bot) -> None:
        self._bot = bot

    def get_client(self) -> _Bot:
        return self._bot


class _Context:
    def __init__(self, bot: _Bot) -> None:
        self._platform = _Platform(bot)

    def get_platform_inst(self, platform_id: str) -> _Platform | None:
        return self._platform if platform_id == "onebot-main" else None


@pytest.mark.asyncio
async def test_scheduler_persists_unique_new_group_file(tmp_path: Path) -> None:
    existing_file = {
        "file_id": "old-file",
        "file_name": "旧本子.pdf",
        "file_size": 10,
    }
    new_file = {
        "file_id": "new-file",
        "file_name": "测试本子.pdf",
        "file_size": 128,
    }
    bot = _Bot([{"files": [existing_file]}, {"files": [existing_file, new_file]}])
    scheduler = RecoverableRevokeScheduler(tmp_path, _Context(bot))
    event = _Event(bot)

    await scheduler.initialize()
    before_file_ids = await scheduler.snapshot_group_file_ids(event)
    assert before_file_ids == frozenset({"old-file"})

    scheduled = await scheduler.schedule_group_file_revoke(
        event,
        before_file_ids=before_file_ids,
        file_name="测试本子.pdf",
        expected_file_size=128,
        delay=1800,
    )

    assert scheduled is True
    stored = json.loads(scheduler.storage_path.read_text(encoding="utf-8"))
    assert stored["version"] == 1
    assert stored["tasks"][0]["platform_id"] == "onebot-main"
    assert stored["tasks"][0]["target"] == "group_file"
    assert stored["tasks"][0]["group_id"] == "10001"
    assert stored["tasks"][0]["file_id"] == "new-file"
    assert stored["tasks"][0]["file_name"] == "测试本子.pdf"
    await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_persists_pending_file_when_napcat_is_still_uploading(
    tmp_path: Path,
) -> None:
    existing_file = {
        "file_id": "old-file",
        "file_name": "旧本子.pdf",
        "file_size": 10,
    }
    bot = _Bot([{"files": [existing_file]}, {"files": [existing_file]}])
    scheduler = RecoverableRevokeScheduler(tmp_path, _Context(bot))
    event = _Event(bot)

    await scheduler.initialize()
    before_file_ids = await scheduler.snapshot_group_file_ids(event)
    scheduled = await scheduler.schedule_group_file_revoke(
        event,
        before_file_ids=before_file_ids or frozenset(),
        file_name="测试本子.pdf",
        expected_file_size=128,
        delay=1800,
    )

    assert scheduled is True
    stored = json.loads(scheduler.storage_path.read_text(encoding="utf-8"))
    assert stored["tasks"] == [
        {
            "task_id": stored["tasks"][0]["task_id"],
            "target": "group_file",
            "platform_id": "onebot-main",
            "due_at": stored["tasks"][0]["due_at"],
            "group_id": "10001",
            "file_name": "测试本子.pdf",
            "before_file_ids": ["old-file"],
            "expected_file_size": 128,
        }
    ]
    await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_resolves_pending_file_at_due_time(tmp_path: Path) -> None:
    storage_path = tmp_path / "revoke_tasks.json"
    storage_path.write_text(
        json.dumps(
            {
                "version": 1,
                "tasks": [
                    {
                        "task_id": "pending-file-task",
                        "target": "group_file",
                        "platform_id": "onebot-main",
                        "group_id": "10001",
                        "file_name": "测试本子.pdf",
                        "before_file_ids": ["old-file"],
                        "expected_file_size": 128,
                        "due_at": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    bot = _Bot(
        [
            {
                "files": [
                    {"file_id": "old-file", "file_name": "旧本子.pdf", "file_size": 10},
                    {
                        "file_id": "new-file",
                        "file_name": "测试本子.pdf",
                        "file_size": 128,
                    },
                ]
            }
        ]
    )
    scheduler = RecoverableRevokeScheduler(tmp_path, _Context(bot))

    await scheduler.initialize()
    await asyncio.gather(*tuple(scheduler._tasks.values()))

    assert (
        "delete_group_file",
        {"group_id": "10001", "file_id": "new-file"},
    ) in bot.calls
    assert json.loads(storage_path.read_text(encoding="utf-8")) == {
        "version": 1,
        "tasks": [],
    }
    await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_restores_due_task_and_deletes_file(tmp_path: Path) -> None:
    storage_path = tmp_path / "revoke_tasks.json"
    storage_path.write_text(
        json.dumps(
            {
                "version": 1,
                "tasks": [
                    {
                        "task_id": "restore-task",
                        "target": "group_file",
                        "platform_id": "onebot-main",
                        "group_id": "10001",
                        "file_id": "expired-file",
                        "file_name": "过期本子.pdf",
                        "due_at": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    bot = _Bot([])
    scheduler = RecoverableRevokeScheduler(tmp_path, _Context(bot))

    await scheduler.initialize()
    await asyncio.gather(*tuple(scheduler._tasks.values()))

    assert (
        "delete_group_file",
        {"group_id": "10001", "file_id": "expired-file"},
    ) in bot.calls
    stored = json.loads(storage_path.read_text(encoding="utf-8"))
    assert stored == {"version": 1, "tasks": []}
    await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_restores_due_message_revoke(tmp_path: Path) -> None:
    storage_path = tmp_path / "revoke_tasks.json"
    storage_path.write_text(
        json.dumps(
            {
                "version": 1,
                "tasks": [
                    {
                        "task_id": "message-task",
                        "target": "message",
                        "platform_id": "onebot-main",
                        "message_id": "7788",
                        "due_at": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    bot = _Bot([])
    scheduler = RecoverableRevokeScheduler(tmp_path, _Context(bot))

    await scheduler.initialize()
    await asyncio.gather(*tuple(scheduler._tasks.values()))

    assert ("delete_msg", {"message_id": "7788"}) in bot.calls
    assert json.loads(storage_path.read_text(encoding="utf-8")) == {
        "version": 1,
        "tasks": [],
    }
    await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_drops_record_after_three_consecutive_delete_failures(
    tmp_path: Path,
) -> None:
    storage_path = tmp_path / "revoke_tasks.json"
    storage_path.write_text(
        json.dumps(
            {
                "version": 1,
                "tasks": [
                    {
                        "task_id": "failing-message-task",
                        "target": "message",
                        "platform_id": "onebot-main",
                        "message_id": "7788",
                        "due_at": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    bot = _Bot([], delete_fails=True)
    context = _Context(bot)

    for expected_failure_count in (1, 2):
        scheduler = RecoverableRevokeScheduler(tmp_path, context)
        await scheduler.initialize()
        await asyncio.gather(*tuple(scheduler._tasks.values()))

        stored = json.loads(storage_path.read_text(encoding="utf-8"))
        assert stored["tasks"][0]["failure_count"] == expected_failure_count
        await scheduler.stop()

    scheduler = RecoverableRevokeScheduler(tmp_path, context)
    await scheduler.initialize()
    await asyncio.gather(*tuple(scheduler._tasks.values()))

    assert json.loads(storage_path.read_text(encoding="utf-8")) == {
        "version": 1,
        "tasks": [],
    }
    assert sum(action == "delete_msg" for action, _ in bot.calls) == 3
    await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_migrates_legacy_doujinshi_cleanup_queue(
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "doujinshi_file_cleanup_tasks.json"
    legacy_path.write_text(
        json.dumps(
            {
                "version": 1,
                "tasks": [
                    {
                        "task_id": "legacy-file-task",
                        "platform_id": "onebot-main",
                        "group_id": "10001",
                        "file_id": "legacy-file",
                        "file_name": "旧本子.pdf",
                        "due_at": 1800,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    scheduler = RecoverableRevokeScheduler(tmp_path, _Context(_Bot([])))

    await scheduler.initialize()

    stored = json.loads(scheduler.storage_path.read_text(encoding="utf-8"))
    assert stored["tasks"] == [
        {
            "task_id": "legacy-file-task",
            "target": "group_file",
            "platform_id": "onebot-main",
            "due_at": 1800.0,
            "group_id": "10001",
            "file_id": "legacy-file",
            "file_name": "旧本子.pdf",
        }
    ]
    assert legacy_path.exists() is False
    await scheduler.stop()
