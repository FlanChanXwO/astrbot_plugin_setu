"""可跨插件重启恢复的 OneBot 撤回与群文件删除调度。"""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from time import time
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

from astrbot.api.event import AstrMessageEvent

from ...shared import get_logger
from .platform_capabilities import is_onebot_like_platform

logger = get_logger()

_STORAGE_NAME = "revoke_tasks.json"
_LEGACY_DOUJINSHI_STORAGE_NAME = "doujinshi_file_cleanup_tasks.json"
_MESSAGE_TARGET = "message"
_GROUP_FILE_TARGET = "group_file"
_MAX_CONSECUTIVE_FAILURES = 3


@dataclass(frozen=True, slots=True)
class GroupFile:
    """OneBot 群根目录中的文件摘要。"""

    file_id: str
    file_name: str
    file_size: int | None


@dataclass(frozen=True, slots=True)
class RevokeTask:
    """可恢复的 OneBot 删除任务。"""

    task_id: str
    target: str
    platform_id: str
    due_at: float
    message_id: str | None = None
    group_id: str | None = None
    file_id: str | None = None
    file_name: str | None = None
    before_file_ids: tuple[str, ...] = ()
    expected_file_size: int | None = None
    failure_count: int = 0

    def to_dict(self) -> dict[str, object]:
        """序列化为 JSON 存储结构。"""
        payload: dict[str, object] = {
            "task_id": self.task_id,
            "target": self.target,
            "platform_id": self.platform_id,
            "due_at": self.due_at,
        }
        if self.message_id is not None:
            payload["message_id"] = self.message_id
        if self.group_id is not None:
            payload["group_id"] = self.group_id
        if self.file_id is not None:
            payload["file_id"] = self.file_id
        if self.file_name is not None:
            payload["file_name"] = self.file_name
        if self.target == _GROUP_FILE_TARGET and self.file_id is None:
            payload["before_file_ids"] = list(self.before_file_ids)
            if self.expected_file_size is not None:
                payload["expected_file_size"] = self.expected_file_size
        if self.failure_count:
            payload["failure_count"] = self.failure_count
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> RevokeTask:
        """从 JSON 存储结构恢复任务。"""
        target = _required_text(payload, "target")
        task_id = _required_text(payload, "task_id")
        platform_id = _required_text(payload, "platform_id")
        due_at = _required_due_at(payload)
        failure_count = _optional_failure_count(payload.get("failure_count"))

        if target == _MESSAGE_TARGET:
            return cls(
                task_id=task_id,
                target=target,
                platform_id=platform_id,
                due_at=due_at,
                message_id=_required_text(payload, "message_id"),
                failure_count=failure_count,
            )
        if target == _GROUP_FILE_TARGET:
            raw_file_id = payload.get("file_id")
            if raw_file_id is None and "before_file_ids" not in payload:
                raise ValueError("待识别群文件任务缺少 before_file_ids")
            return cls(
                task_id=task_id,
                target=target,
                platform_id=platform_id,
                due_at=due_at,
                group_id=_required_text(payload, "group_id"),
                file_id=(
                    _required_text(payload, "file_id")
                    if raw_file_id is not None
                    else None
                ),
                file_name=_required_text(payload, "file_name"),
                before_file_ids=_optional_file_ids(payload.get("before_file_ids")),
                expected_file_size=_optional_file_size(
                    payload.get("expected_file_size")
                ),
                failure_count=failure_count,
            )
        raise ValueError(f"不支持的删除目标: {target}")


class RecoverableRevokeScheduler:
    """统一维护消息撤回与群文件删除的持久化任务。"""

    def __init__(self, data_dir: Path | str, context: object) -> None:
        data_path = Path(data_dir)
        self._storage_path = data_path / _STORAGE_NAME
        self._legacy_doujinshi_path = data_path / _LEGACY_DOUJINSHI_STORAGE_NAME
        self._context = context
        self._records: dict[str, RevokeTask] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    @property
    def storage_path(self) -> Path:
        """返回统一撤回任务的持久化文件路径。"""
        return self._storage_path

    async def initialize(self) -> None:
        """加载待删除任务，迁移旧本子队列并按到期时间恢复。"""
        records, migrated_legacy_tasks = await asyncio.to_thread(self._load_records)
        async with self._lock:
            self._records = {record.task_id: record for record in records}
            if migrated_legacy_tasks:
                await self._persist_records()
                await asyncio.to_thread(self._legacy_doujinshi_path.unlink)
            for record in records:
                self._schedule_record(record)

    async def stop(self) -> None:
        """停止内存计时协程，保留持久化任务供下次启动恢复。"""
        tasks = tuple(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def schedule_revoke(
        self,
        event: AstrMessageEvent,
        message_id: str,
        delay: int,
    ) -> bool:
        """持久化登记一条 OneBot 消息撤回任务。"""
        normalized_id = str(message_id or "").strip()
        if not normalized_id:
            logger.warning("[revoke] 跳过登记：message_id 为空")
            return False
        if not _is_onebot_event(event):
            logger.warning(
                "[revoke] 跳过登记：当前平台不是 OneBot，message_id=%s", normalized_id
            )
            return False

        platform_id = _event_text(event, "get_platform_id")
        if not platform_id:
            logger.warning(
                "[revoke] 跳过登记：缺少平台 ID，message_id=%s", normalized_id
            )
            return False

        try:
            client = _event_client(event)
        except RuntimeError as exc:
            logger.warning("[revoke] 跳过登记：%s", exc)
            return False
        if not _supports_delete_msg(client):
            logger.warning(
                "[revoke] 跳过登记：delete_msg 不受支持，message_id=%s", normalized_id
            )
            return False

        record = RevokeTask(
            task_id=uuid4().hex,
            target=_MESSAGE_TARGET,
            platform_id=platform_id,
            due_at=time() + max(0, int(delay)),
            message_id=normalized_id,
        )
        await self._register(record)
        logger.info(
            "[revoke] 已登记可恢复消息撤回: platform_id=%s, message_id=%s, delay=%ss",
            platform_id,
            normalized_id,
            delay,
        )
        return True

    async def snapshot_group_file_ids(
        self, event: AstrMessageEvent
    ) -> frozenset[str] | None:
        """读取发送前的群根目录文件 ID，用于发送后识别新增文件。"""
        if not _is_onebot_event(event):
            return None
        try:
            files = await self._list_group_files(event)
        except Exception as exc:
            logger.warning("[revoke] 无法读取发送前群文件列表: %s", exc)
            return None
        return frozenset(file.file_id for file in files)

    async def schedule_group_file_revoke(
        self,
        event: AstrMessageEvent,
        *,
        before_file_ids: frozenset[str],
        file_name: str,
        expected_file_size: int | None,
        delay: int,
    ) -> bool:
        """持久化群文件删除任务，并在可见时提前锁定文件 ID。"""
        if delay <= 0:
            return False
        if not _is_onebot_event(event):
            logger.warning("[revoke] 跳过群文件登记：当前平台不是 OneBot")
            return False

        group_id = _event_text(event, "get_group_id")
        platform_id = _event_text(event, "get_platform_id")
        normalized_name = file_name.strip()
        if not group_id or not platform_id or not normalized_name:
            logger.warning("[revoke] 跳过群文件登记：缺少群号、平台 ID 或文件名")
            return False

        record = RevokeTask(
            task_id=uuid4().hex,
            target=_GROUP_FILE_TARGET,
            platform_id=platform_id,
            due_at=time() + delay,
            group_id=group_id,
            file_name=normalized_name,
            before_file_ids=tuple(sorted(before_file_ids)),
            expected_file_size=expected_file_size,
        )
        await self._register(record)

        try:
            file_id = await self._resolve_group_file_id(_event_client(event), record)
        except Exception as exc:
            logger.warning(
                "[revoke] 发送后无法读取群文件列表；已保留待识别任务: "
                "group_id=%s, file_name=%s, error=%s",
                group_id,
                normalized_name,
                exc,
            )
            return True

        if file_id is None:
            logger.info(
                "[revoke] 群文件暂未可见；已保留待识别任务至到期删除: "
                "group_id=%s, file_name=%s",
                group_id,
                normalized_name,
            )
            return True

        await self._replace_record(replace(record, file_id=file_id))
        logger.info(
            "[revoke] 已登记可恢复群文件删除: group_id=%s, file_id=%s, delay=%ss",
            group_id,
            file_id,
            delay,
        )
        return True

    async def _register(self, record: RevokeTask) -> None:
        async with self._lock:
            self._records[record.task_id] = record
            await self._persist_records()
            self._schedule_record(record)

    async def _replace_record(self, record: RevokeTask) -> None:
        """用已解析的目标信息更新已持久化任务。"""
        async with self._lock:
            if record.task_id not in self._records:
                return
            self._records[record.task_id] = record
            await self._persist_records()

    async def _list_group_files(self, event: AstrMessageEvent) -> tuple[GroupFile, ...]:
        group_id = _event_text(event, "get_group_id")
        if not group_id:
            raise ValueError("当前消息不是群聊")
        return await self._list_group_files_for_group(_event_client(event), group_id)

    async def _list_group_files_for_group(
        self, client: Any, group_id: str
    ) -> tuple[GroupFile, ...]:
        response = await _call_onebot_action(
            client, "get_group_root_files", group_id=group_id
        )
        return _parse_group_files(response)

    async def _resolve_group_file_id(
        self, client: Any, record: RevokeTask
    ) -> str | None:
        """根据发送前快照和文件特征定位唯一新增群文件。"""
        files = await self._list_group_files_for_group(
            client, _required_task_value(record.group_id)
        )
        candidates = _new_group_file_candidates(files, record)
        return candidates[0].file_id if len(candidates) == 1 else None

    def _schedule_record(self, record: RevokeTask) -> None:
        if record.task_id in self._tasks:
            return
        task = asyncio.create_task(
            self._delete_when_due(record.task_id, record.due_at),
            name=f"setu_revoke_{record.target}_{record.task_id}",
        )
        self._tasks[record.task_id] = task
        task.add_done_callback(
            lambda completed, task_id=record.task_id: self._tasks.pop(task_id, None)
        )

    async def _delete_when_due(self, task_id: str, due_at: float) -> None:
        record: RevokeTask | None = None
        try:
            await asyncio.sleep(max(0.0, due_at - time()))
            async with self._lock:
                record = self._records.get(task_id)
            if record is None:
                return
            client = self._get_client_for_task(record)
            if record.target == _MESSAGE_TARGET:
                await _call_delete_msg(client, _required_task_value(record.message_id))
            else:
                file_id = record.file_id
                if file_id is None:
                    file_id = await self._resolve_group_file_id(client, record)
                if file_id is None:
                    raise RuntimeError(
                        "到期时未能唯一识别本子群文件: "
                        f"group_id={record.group_id}, file_name={record.file_name}"
                    )
                await _call_onebot_action(
                    client,
                    "delete_group_file",
                    group_id=_required_task_value(record.group_id),
                    file_id=file_id,
                )
        except asyncio.CancelledError:
            logger.debug("[revoke] 已停止等待删除: task_id=%s", task_id)
            raise
        except Exception as exc:
            if record is None:
                logger.warning(
                    "[revoke] 删除任务启动失败，无法登记失败次数: task_id=%s, error=%s",
                    task_id,
                    exc,
                )
                return
            failure_state = await self._record_delete_failure(record)
            if failure_state is None:
                logger.warning(
                    "[revoke] 删除失败，但任务已不在队列中: "
                    "task_id=%s, target=%s, error=%s",
                    record.task_id,
                    record.target,
                    exc,
                )
                return
            failure_count, removed = failure_state
            if removed:
                logger.warning(
                    "[revoke] 删除连续失败达到上限，已移除任务记录: "
                    "task_id=%s, target=%s, failure_count=%s, error=%s",
                    record.task_id,
                    record.target,
                    failure_count,
                    exc,
                )
            else:
                logger.warning(
                    "[revoke] 删除失败，保留任务供下次启动恢复: "
                    "task_id=%s, target=%s, failure_count=%s/%s, error=%s",
                    record.task_id,
                    record.target,
                    failure_count,
                    _MAX_CONSECUTIVE_FAILURES,
                    exc,
                )
            return

        async with self._lock:
            if self._records.pop(task_id, None) is not None:
                await self._persist_records()
        logger.info(
            "[revoke] 已执行删除: task_id=%s, target=%s",
            record.task_id,
            record.target,
        )

    async def _record_delete_failure(
        self, record: RevokeTask
    ) -> tuple[int, bool] | None:
        """持久化一次实际删除失败，并在第三次失败时丢弃任务。"""
        async with self._lock:
            current = self._records.get(record.task_id)
            if current is None:
                return None
            failure_count = current.failure_count + 1
            reached_limit = failure_count >= _MAX_CONSECUTIVE_FAILURES
            if reached_limit:
                self._records.pop(record.task_id)
            else:
                self._records[record.task_id] = replace(
                    current, failure_count=failure_count
                )
            await self._persist_records()
        return failure_count, reached_limit

    def _get_client_for_task(self, record: RevokeTask) -> Any:
        get_platform_inst = _callable_attr(self._context, "get_platform_inst")
        if get_platform_inst is None:
            raise RuntimeError("AstrBot context 不支持按平台 ID 获取适配器")
        platform = get_platform_inst(record.platform_id)
        if platform is None:
            raise RuntimeError(f"找不到平台适配器: {record.platform_id}")
        get_client = _callable_attr(platform, "get_client")
        if get_client is None:
            raise RuntimeError(f"平台不支持 OneBot 客户端: {record.platform_id}")
        return get_client()

    async def _persist_records(self) -> None:
        await asyncio.to_thread(self._write_records, tuple(self._records.values()))

    def _load_records(self) -> tuple[tuple[RevokeTask, ...], bool]:
        records = self._load_current_records()
        legacy_records = self._load_legacy_doujinshi_records()
        if not legacy_records:
            return records, False

        merged_records = {record.task_id: record for record in records}
        for legacy_record in legacy_records:
            current_record = merged_records.get(legacy_record.task_id)
            if current_record is None:
                merged_records[legacy_record.task_id] = legacy_record
            elif current_record != legacy_record:
                raise RuntimeError("撤回任务与旧本子清理任务存在冲突 ID")
        return tuple(merged_records.values()), True

    def _load_current_records(self) -> tuple[RevokeTask, ...]:
        payload = _load_json_payload(self._storage_path, "撤回任务")
        if payload is None:
            return ()
        if payload.get("version") != 1:
            raise RuntimeError("撤回任务文件格式或版本无效")
        raw_records = payload.get("tasks")
        if not isinstance(raw_records, list):
            raise RuntimeError("撤回任务文件缺少 tasks 列表")
        return _parse_task_records(raw_records, RevokeTask.from_dict, "撤回任务")

    def _load_legacy_doujinshi_records(self) -> tuple[RevokeTask, ...]:
        payload = _load_json_payload(self._legacy_doujinshi_path, "旧本子清理任务")
        if payload is None:
            return ()
        if payload.get("version") != 1:
            raise RuntimeError("旧本子清理任务文件格式或版本无效")
        raw_records = payload.get("tasks")
        if not isinstance(raw_records, list):
            raise RuntimeError("旧本子清理任务文件缺少 tasks 列表")
        return _parse_task_records(
            raw_records,
            _legacy_doujinshi_task_from_dict,
            "旧本子清理任务",
        )

    def _write_records(self, records: tuple[RevokeTask, ...]) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "tasks": [record.to_dict() for record in records],
        }
        temporary_path = self._storage_path.with_name(
            f".{self._storage_path.name}.{uuid4().hex}.tmp"
        )
        try:
            temporary_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary_path.replace(self._storage_path)
        finally:
            temporary_path.unlink(missing_ok=True)


_scheduler: RecoverableRevokeScheduler | None = None


async def init_revoke_scheduler(
    data_dir: Path | str,
    context: object,
) -> RecoverableRevokeScheduler:
    """初始化统一可恢复撤回调度器。"""
    global _scheduler
    if _scheduler is not None:
        await _scheduler.stop()
    _scheduler = RecoverableRevokeScheduler(data_dir, context)
    await _scheduler.initialize()
    return _scheduler


def get_revoke_scheduler() -> RecoverableRevokeScheduler | None:
    """返回已初始化的统一可恢复撤回调度器。"""
    return _scheduler


async def stop_revoke_scheduler() -> None:
    """停止内存计时协程，保留任务供下一次启动恢复。"""
    global _scheduler
    if _scheduler is None:
        return
    await _scheduler.stop()
    _scheduler = None


async def schedule_revoke(
    event: AstrMessageEvent,
    message_id: str,
    delay: int,
) -> bool:
    """通过统一可恢复调度器登记消息撤回。"""
    scheduler = get_revoke_scheduler()
    if scheduler is None:
        logger.warning("[revoke] 调度器尚未初始化，未登记 message_id=%s", message_id)
        return False
    return await scheduler.schedule_revoke(event, message_id, delay)


def _legacy_doujinshi_task_from_dict(payload: Mapping[str, object]) -> RevokeTask:
    return RevokeTask(
        task_id=_required_text(payload, "task_id"),
        target=_GROUP_FILE_TARGET,
        platform_id=_required_text(payload, "platform_id"),
        due_at=_required_due_at(payload),
        group_id=_required_text(payload, "group_id"),
        file_id=_required_text(payload, "file_id"),
        file_name=_required_text(payload, "file_name"),
    )


def _load_json_payload(path: Path, label: str) -> Mapping[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取{label}文件: {path}") from exc
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"{label}文件根节点无效")
    return payload


def _parse_task_records(
    raw_records: list[object],
    parser: Any,
    label: str,
) -> tuple[RevokeTask, ...]:
    records: list[RevokeTask] = []
    for index, item in enumerate(raw_records):
        if not isinstance(item, Mapping):
            raise RuntimeError(f"{label} #{index} 格式无效")
        try:
            records.append(parser(item))
        except ValueError as exc:
            raise RuntimeError(f"{label} #{index} 格式无效") from exc
    if len({record.task_id for record in records}) != len(records):
        raise RuntimeError(f"{label}文件包含重复任务 ID")
    return tuple(records)


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} 必须是非空字符串")
    return value.strip()


def _required_due_at(payload: Mapping[str, object]) -> float:
    due_at = payload.get("due_at")
    if not isinstance(due_at, int | float) or isinstance(due_at, bool):
        raise ValueError("due_at 必须是数字")
    return float(due_at)


def _optional_file_ids(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("before_file_ids 必须是列表")
    file_ids = tuple(
        item.strip() for item in value if isinstance(item, str) and item.strip()
    )
    if len(file_ids) != len(value) or len(set(file_ids)) != len(file_ids):
        raise ValueError("before_file_ids 必须由不重复的非空字符串组成")
    return file_ids


def _optional_file_size(value: object) -> int | None:
    if value is None:
        return None
    parsed = _parse_file_size(value)
    if parsed is None:
        raise ValueError("expected_file_size 必须是非负整数")
    return parsed


def _optional_failure_count(value: object) -> int:
    if value is None:
        return 0
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("failure_count 必须是非负整数")
    return value


def _required_task_value(value: str | None) -> str:
    if value is None:
        raise RuntimeError("持久化撤回任务缺少必要目标字段")
    return value


def _event_text(event: AstrMessageEvent, method_name: str) -> str:
    method = _callable_attr(event, method_name)
    if method is None:
        return ""
    value = method()
    return str(value).strip() if value else ""


def _is_onebot_event(event: AstrMessageEvent) -> bool:
    return is_onebot_like_platform(_platform_name(event))


def _platform_name(event: AstrMessageEvent) -> str | None:
    platform = getattr(event, "platform", None)
    name = getattr(platform, "name", None)
    if isinstance(name, str) and name:
        return name
    getter = _callable_attr(event, "get_platform_name")
    if getter is None:
        return None
    value = getter()
    return str(value) if value else None


def _event_client(event: AstrMessageEvent) -> Any:
    client = getattr(event, "bot", None) or getattr(event, "_bot", None)
    if client is None:
        raise RuntimeError("当前事件不提供 OneBot 客户端")
    return client


def _supports_delete_msg(client: Any) -> bool:
    return (
        _callable_attr(client, "delete_msg") is not None
        or _callable_attr(getattr(client, "api", None), "call_action") is not None
        or _callable_attr(client, "call_action") is not None
    )


async def _call_delete_msg(client: Any, message_id: str) -> Any:
    delete_msg = _callable_attr(client, "delete_msg")
    if delete_msg is not None:
        return await _maybe_await(delete_msg(message_id=message_id))
    return await _call_onebot_action(client, "delete_msg", message_id=message_id)


async def _call_onebot_action(client: Any, action: str, **kwargs: object) -> Any:
    call_action = _callable_attr(client, "call_action")
    if call_action is None:
        call_action = _callable_attr(getattr(client, "api", None), "call_action")
    if call_action is None:
        raise RuntimeError(f"OneBot 客户端不支持 {action}")
    result = await _maybe_await(call_action(action, **kwargs))
    if isinstance(result, Mapping):
        status = result.get("status")
        retcode = result.get("retcode")
        if status in {"failed", "error"} or (
            isinstance(retcode, int) and not isinstance(retcode, bool) and retcode != 0
        ):
            raise RuntimeError(f"OneBot action {action} 返回失败: {result}")
    return result


def _parse_group_files(response: object) -> tuple[GroupFile, ...]:
    files: list[GroupFile] = []
    for item in _group_file_items(response):
        if not isinstance(item, Mapping):
            continue
        file_id = item.get("file_id")
        file_name = item.get("file_name")
        if not isinstance(file_id, str) or not file_id:
            continue
        if not isinstance(file_name, str) or not file_name:
            continue
        files.append(
            GroupFile(
                file_id=file_id,
                file_name=file_name,
                file_size=_parse_file_size(item.get("file_size")),
            )
        )
    return tuple(files)


def _group_file_items(response: object) -> list[object]:
    payload = response
    if isinstance(payload, Mapping) and isinstance(payload.get("data"), Mapping | list):
        payload = payload["data"]
    if isinstance(payload, Mapping):
        for key in ("files", "root_files"):
            files = payload.get(key)
            if isinstance(files, list):
                return files
    return payload if isinstance(payload, list) else []


def _parse_file_size(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value if value >= 0 else None
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _matches_expected_size(actual: int | None, expected: int | None) -> bool:
    return actual is None or expected is None or actual == expected


def _new_group_file_candidates(
    files: tuple[GroupFile, ...], record: RevokeTask
) -> list[GroupFile]:
    """筛选发送快照之后出现且与待删除 PDF 一致的群文件。"""
    file_name = _required_task_value(record.file_name)
    before_file_ids = frozenset(record.before_file_ids)
    return [
        file
        for file in files
        if file.file_id not in before_file_ids
        and file.file_name == file_name
        and _matches_expected_size(file.file_size, record.expected_file_size)
    ]


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _callable_attr(obj: object | None, name: str) -> Any | None:
    if obj is None:
        return None
    # MagicMock 会为任意属性动态创建可调用替身；只把测试中明确配置的
    # action 当作平台能力，避免把不存在的 delete_msg 误判为可用接口。
    if isinstance(obj, Mock) and name not in vars(obj):
        mock_children = getattr(obj, "_mock_children", {})
        if name not in mock_children:
            return None
    value = getattr(obj, name, None)
    return value if callable(value) else None


__all__ = [
    "RecoverableRevokeScheduler",
    "RevokeTask",
    "get_revoke_scheduler",
    "init_revoke_scheduler",
    "schedule_revoke",
    "stop_revoke_scheduler",
]
