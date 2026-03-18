"""图片发送混入类。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

import astrbot.api.message_components as Comp
from astrbot.api import logger

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent


class SendWithRevokeMixin:
    """支持撤回的消息发送混入类。"""

    def _get_bot_api(self, event: AstrMessageEvent) -> Any | None:
        """从事件中获取底层 bot API 客户端。"""
        return getattr(event, "bot", None)

    async def _send_with_revoke_support(
        self,
        event: AstrMessageEvent,
        chain: list[Any],
        is_group: bool,
        session_id: str,
    ) -> str | None:
        """发送消息并返回 message_id 以支持撤回。"""
        try:
            bot = self._get_bot_api(event)
            if not bot:
                return None

            messages = []
            for comp in chain:
                if isinstance(comp, Comp.Plain):
                    if comp.text.strip():
                        messages.append({"type": "text", "data": {"text": comp.text}})
                elif isinstance(comp, Comp.Image):
                    if comp.file and comp.file.startswith("base64://"):
                        messages.append({"type": "image", "data": {"file": comp.file}})
                    elif comp.file:
                        messages.append({"type": "image", "data": {"file": comp.file}})
                    elif comp.url:
                        messages.append({"type": "image", "data": {"file": comp.url}})
                elif isinstance(comp, Comp.File):
                    if comp.file:
                        messages.append({"type": "file", "data": {"file": comp.file}})

            if not messages:
                return None

            if is_group:
                result = await bot.call_action(
                    "send_group_msg",
                    group_id=int(session_id) if session_id.isdigit() else session_id,
                    message=messages,
                )
            else:
                result = await bot.call_action(
                    "send_private_msg",
                    user_id=int(session_id) if session_id.isdigit() else session_id,
                    message=messages,
                )

            if isinstance(result, dict):
                data = result.get("data", result)
                message_id = data.get("message_id") if isinstance(data, dict) else None
                if message_id:
                    return str(message_id)
            return None
        except Exception:
            logger.exception("[revoke] Failed to send with revoke support")
            return None

    async def _send_file_with_revoke(
        self, event: AstrMessageEvent, file_path: str, file_name: str
    ) -> str | None:
        """发送文件并返回 message_id。"""
        try:
            import base64

            bot = self._get_bot_api(event)
            if not bot:
                return None

            is_group = bool(event.get_group_id())
            session_id = event.get_group_id() or event.get_sender_id()

            path_obj = Path(file_path)
            file_size = path_obj.stat().st_size
            max_size = 5 * 1024 * 1024

            if file_size > max_size:
                logger.warning("[revoke] File too large (%d bytes)", file_size)
                return None

            file_data = path_obj.read_bytes()
            file_b64 = base64.b64encode(file_data).decode()

            messages = [
                {
                    "type": "file",
                    "data": {"file": f"base64://{file_b64}", "name": file_name},
                }
            ]

            if is_group:
                result = await bot.call_action(
                    "send_group_msg",
                    group_id=int(session_id)
                    if str(session_id).isdigit()
                    else session_id,
                    message=messages,
                )
            else:
                result = await bot.call_action(
                    "send_private_msg",
                    user_id=int(session_id)
                    if str(session_id).isdigit()
                    else session_id,
                    message=messages,
                )

            if isinstance(result, dict):
                data = result.get("data", result)
                message_id = data.get("message_id") if isinstance(data, dict) else None
                if message_id:
                    return str(message_id)
            return None
        except (OSError, RuntimeError):
            logger.exception("[revoke] Failed to send file with revoke support")
            return None

    async def _send_nodes_with_revoke(
        self, event: AstrMessageEvent, nodes: list[Comp.Node]
    ) -> str | None:
        """发送合并转发消息并返回 message_id。优化版本：并行转换 node 到 dict。"""
        import time

        start_time = time.monotonic()

        try:
            bot = self._get_bot_api(event)
            if not bot:
                logger.warning("[forward] No bot API available for revoke support")
                return None

            is_group = bool(event.get_group_id())
            session_id = event.get_group_id() or event.get_sender_id()

            # 并行转换所有 nodes 到 dict，提高效率
            tasks = [node.to_dict() for node in nodes]
            messages = await asyncio.gather(*tasks)

            dict_time = time.monotonic()
            logger.debug(
                "[forward] Converted %d nodes to dict in %.3fs", len(nodes), dict_time - start_time
            )

            if is_group:
                result = await bot.call_action(
                    "send_group_forward_msg",
                    group_id=int(session_id)
                    if str(session_id).isdigit()
                    else session_id,
                    messages=messages,
                )
            else:
                result = await bot.call_action(
                    "send_private_forward_msg",
                    user_id=int(session_id)
                    if str(session_id).isdigit()
                    else session_id,
                    messages=messages,
                )

            end_time = time.monotonic()

            # 检查 API 返回结果
            if isinstance(result, dict):
                # 检查是否有错误返回
                if result.get("status") == "failed" or result.get("retcode") not in (0, None):
                    logger.warning(
                        "[forward] API returned failure: %s", result
                    )
                    return None

            logger.info(
                "[forward] Sent %d nodes in %.3fs (dict: %.3fs, api: %.3fs)",
                len(nodes),
                end_time - start_time,
                dict_time - start_time,
                end_time - dict_time,
            )

            if isinstance(result, dict):
                data = result.get("data", result)
                message_id = data.get("message_id") if isinstance(data, dict) else None
                if message_id:
                    return str(message_id)
            return None
        except (OSError, RuntimeError):
            logger.exception("[revoke] Failed to send nodes with revoke support")
            return None

    async def _send_nodes_direct(
        self, event: AstrMessageEvent, nodes: list[Comp.Node]
    ) -> bool:
        """直接发送合并转发消息（无撤回支持），优化版本。

        注意：合并转发消息仅在 OneBot v11 等特定平台受支持。
        对于不支持的平台，会返回 False，调用方应降级为普通发送。
        """
        import time

        start_time = time.monotonic()

        try:
            bot = self._get_bot_api(event)
            if not bot:
                logger.warning("[forward] No bot API available")
                return False

            is_group = bool(event.get_group_id())
            session_id = event.get_group_id() or event.get_sender_id()

            # 并行转换所有 nodes 到 dict
            tasks = [node.to_dict() for node in nodes]
            messages = await asyncio.gather(*tasks)

            dict_time = time.monotonic()
            logger.debug(
                "[forward] Converted %d nodes to dict in %.3fs",
                len(nodes),
                dict_time - start_time,
            )

            # 调用发送 API
            if is_group:
                result = await bot.call_action(
                    "send_group_forward_msg",
                    group_id=int(session_id)
                    if str(session_id).isdigit()
                    else session_id,
                    messages=messages,
                )
            else:
                result = await bot.call_action(
                    "send_private_forward_msg",
                    user_id=int(session_id)
                    if str(session_id).isdigit()
                    else session_id,
                    messages=messages,
                )

            end_time = time.monotonic()

            # 检查结果，某些平台会返回错误或特定状态表示不支持
            if isinstance(result, dict):
                # 检查是否有错误返回
                if result.get("status") == "failed" or result.get("retcode") not in (0, None):
                    logger.warning(
                        "[forward] API returned failure: %s", result
                    )
                    return False
                # 检查 message_id 是否存在（某些平台可能不支持）
                data = result.get("data", result)
                if not data or (isinstance(data, dict) and not data.get("message_id")):
                    logger.warning(
                        "[forward] API returned no message_id, platform may not support forward messages"
                    )
                    return False

            logger.info(
                "[forward] Sent %d nodes in %.3fs (dict: %.3fs, api: %.3fs)",
                len(nodes),
                end_time - start_time,
                dict_time - start_time,
                end_time - dict_time,
            )
            return True
        except Exception as exc:
            logger.exception("[forward] Failed to send nodes direct: %s", exc)
            return False
