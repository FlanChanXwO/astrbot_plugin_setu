"""Setu 插件核心逻辑。"""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from .config import SetuConfig
from .docx_service import DocxService
from .html_renderer import HtmlCardRenderer
from .image_service import ImageService, UrlImageDiskCache
from .providers import get_provider
from .session_config import SessionConfigManager


class RevokeManager:
    """管理 revoke.json，用于追踪被撤回的 R18 消息。"""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.revoke_file = data_dir / "revoke.json"
        self._lock = asyncio.Lock()
        self._data: dict[str, Any] = {"entries": {}, "meta": {}}

    async def initialize(self) -> None:
        """初始化 revoke.json 文件。"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        await self._load()

    async def _load(self) -> None:
        """从文件加载撤回数据。"""
        if not self.revoke_file.exists():
            self._data = {"entries": {}, "meta": {"created_at": int(time.time())}}
            await self._save()
            return
        try:
            async with self._lock:
                content = self.revoke_file.read_text(encoding="utf-8")
                loaded = json.loads(content)
                self._data = {
                    "entries": loaded.get("entries", {}),
                    "meta": loaded.get("meta", {}),
                }
        except (OSError, json.JSONDecodeError):
            logger.exception("[revoke] Failed to load revoke.json, creating new")
            self._data = {"entries": {}, "meta": {"created_at": int(time.time())}}
            await self._save()

    async def _save(self) -> None:
        """将撤回数据保存到文件。"""
        try:
            tmp_path = self.revoke_file.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(self.revoke_file)
        except OSError:
            logger.exception("[revoke] Failed to save revoke.json")

    async def add_entry(
        self,
        message_id: str,
        platform: str,
        session_id: str,
        is_group: bool,
        revoke_time: int,
    ) -> None:
        """添加一个需要撤回的新条目。"""
        async with self._lock:
            self._data["entries"][message_id] = {
                "message_id": message_id,
                "platform": platform,
                "session_id": session_id,
                "is_group": is_group,
                "revoke_time": revoke_time,
                "created_at": int(time.time()),
                "revoked": False,
            }
            await self._save()
            logger.debug(
                "[revoke] Added entry message_id=%s revoke_time=%d",
                message_id,
                revoke_time,
            )

    async def mark_revoked(self, message_id: str) -> None:
        """将条目标记为已撤回。"""
        async with self._lock:
            if message_id in self._data["entries"]:
                self._data["entries"][message_id]["revoked"] = True
                self._data["entries"][message_id]["revoked_at"] = int(time.time())
                await self._save()
                logger.debug("[revoke] Marked as revoked message_id=%s", message_id)

    def get_pending_entries(self) -> list[dict[str, Any]]:
        """获取所有需要撤回的待处理条目。"""
        now = int(time.time())
        pending = []
        for entry in self._data["entries"].values():
            if not entry.get("revoked", False) and entry.get("revoke_time", 0) <= now:
                pending.append(entry)
        return pending

    async def cleanup_revoked_entries(self, max_age_hours: int = 24) -> int:
        """移除超过 max_age_hours 的已撤回条目，防止文件膨胀。"""
        cutoff = int(time.time()) - (max_age_hours * 3600)
        async with self._lock:
            to_remove = [
                msg_id
                for msg_id, entry in self._data["entries"].items()
                if entry.get("revoked", False) and entry.get("revoked_at", 0) < cutoff
            ]
            for msg_id in to_remove:
                del self._data["entries"][msg_id]
            if to_remove:
                await self._save()
                logger.info(
                    "[revoke] Cleaned up %d old revoked entries", len(to_remove)
                )
            return len(to_remove)


class SetuCore:
    """Setu 插件的业务逻辑处理器。"""

    def __init__(self, plugin, config: SetuConfig, plugin_data_dir: Path):
        self.plugin = plugin
        self._config = config
        self.plugin_data_dir = plugin_data_dir
        self._cache: UrlImageDiskCache | None = None
        self._image_service: ImageService | None = None
        self._docx_service = DocxService()
        self._html_renderer: HtmlCardRenderer | None = None
        self._revoke_manager = RevokeManager(plugin_data_dir)
        self._session_config = SessionConfigManager(plugin_data_dir)
        self._revoke_tasks: set[asyncio.Task] = set()

        if config.enable_html_card:
            template_path = Path(__file__).parent / "templates" / "main.html"
            self._html_renderer = HtmlCardRenderer(template_path)

    async def initialize(self) -> None:
        """初始化缓存和依赖服务。"""
        # 初始化会话配置管理器
        try:
            await self._session_config.initialize()
            cleaned = await self._session_config.cleanup_expired_sessions(
                max_age_days=30
            )
            logger.info(
                "[session_config] SessionConfigManager initialized, cleaned %d sessions",
                cleaned,
            )
        except (OSError, json.JSONDecodeError, RuntimeError):
            logger.exception(
                "[session_config] Failed to initialize SessionConfigManager"
            )

        # 初始化撤回管理器并清理旧条目
        try:
            await self._revoke_manager.initialize()
            # 清理 24 小时之前撤回的条目
            cleaned = await self._revoke_manager.cleanup_revoked_entries(
                max_age_hours=24
            )
            logger.info(
                "[revoke] RevokeManager initialized, cleaned %d old entries", cleaned
            )
            # 恢复调度：检查是否有未处理的 pending entries，立即执行
            await self._restore_pending_revokes()
        except (OSError, json.JSONDecodeError, RuntimeError):
            logger.exception("[revoke] Failed to initialize RevokeManager")

        try:
            if self.config.cache_enabled:
                cache_dir = self.plugin_data_dir / "cache"
                self._cache = UrlImageDiskCache(
                    cache_dir=cache_dir,
                    ttl_hours=self.config.cache_ttl_hours,
                    max_items=self.config.cache_max_items,
                    enabled=True,
                )
                await self._cache.initialize(
                    cleanup_on_start=self.config.cache_cleanup_on_start
                )
                logger.info(
                    "[setu.cache] enabled dir=%s ttl_hours=%d max_items=%d",
                    cache_dir,
                    self.config.cache_ttl_hours,
                    self.config.cache_max_items,
                )
            self._image_service = ImageService(self._cache)
        except (OSError, RuntimeError, ValueError):
            logger.exception(
                "SetuCore initialize failed, fallback to no-cache ImageService"
            )
            self._cache = None
            self._image_service = ImageService(None)

    async def _restore_pending_revokes(self) -> None:
        """恢复未处理的撤回任务（插件重启后）。"""
        try:
            pending = self._revoke_manager.get_pending_entries()
            if not pending:
                return
            logger.info("[revoke] Restoring %d pending revoke tasks", len(pending))
            now = int(time.time())
            for entry in pending:
                message_id = entry.get("message_id")
                revoke_time = entry.get("revoke_time", 0)
                if revoke_time <= now:
                    # 已过期，立即标记为已撤回（无法执行）
                    await self._revoke_manager.mark_revoked(message_id)
                    logger.debug("[revoke] Expired entry marked as revoked: %s", message_id)
                else:
                    # 重新调度
                    delay = revoke_time - now
                    # 无法恢复 bot 引用，所以使用 None
                    task = asyncio.create_task(
                        self._delayed_revoke(
                            message_id, delay,
                            entry.get("platform", ""),
                            entry.get("session_id", ""),
                            entry.get("is_group", False),
                            None, None
                        )
                    )
                    self._revoke_tasks.add(task)
                    task.add_done_callback(self._revoke_tasks.discard)
                    logger.debug("[revoke] Restored revoke task for message %s in %ds", message_id, delay)
        except Exception as exc:
            logger.exception("[revoke] Failed to restore pending revokes: %s", exc)

    def terminate(self) -> None:
        """终止插件，取消所有后台任务。"""
        # 取消所有未完成的撤回任务
        for task in list(self._revoke_tasks):
            if not task.done():
                task.cancel()
        self._revoke_tasks.clear()
        logger.info("[revoke] All revoke tasks cancelled")

    def _get_provider(self):
        cfg = self.config
        lolicon_config = None
        if cfg.api_type in ("lolicon", "all"):
            lolicon_config = {
                "image_size": cfg.image_size,
                "proxy": cfg.proxy,
                "aspect_ratio": cfg.aspect_ratio,
                "uid": cfg.uid,
                "keyword": cfg.keyword,
            }

        return get_provider(
            cfg.api_type,
            custom_config=cfg.custom_api if cfg.api_type == "custom" else None,
            parser_config=cfg.api_response_parser if cfg.api_type == "custom" else None,
            custom_api_configs=cfg.custom_api_configs
            if cfg.api_type in ("custom", "all")
            else None,
            multi_api_strategy=cfg.multi_api_strategy,
            lolicon_config=lolicon_config,
        )

    async def get_effective_content_mode(self, event: AstrMessageEvent) -> str:
        """获取生效的内容模式。

        优先检查会话级别的配置，如果没有设置则使用全局配置。

        Args:
            event: 消息事件对象

        Returns:
            内容模式: sfw/r18/mix
        """
        session_id = event.get_session_id()
        is_group = bool(event.get_group_id())

        # 优先检查会话配置
        session_mode = await self._session_config.get_session_content_mode(
            session_id, is_group
        )
        if session_mode:
            logger.debug(
                "[session_config] Using session content_mode=%s for %s",
                session_mode,
                session_id,
            )
            return session_mode

        # 回退到全局配置
        return self.config.content_mode

    def _determine_r18(self, content_mode: str) -> bool:
        """根据内容模式确定是否为 R18。"""
        if content_mode == "r18":
            return True
        if content_mode == "mix":
            return random.random() > 0.5
        return False

    def _resolve_send_mode(self, send_mode: str, image_count: int) -> str:
        if send_mode == "auto":
            actual_send_mode = "forward" if image_count > 1 else "image"
            logger.info("[auto-send] count=%d mode=%s", image_count, actual_send_mode)
            return actual_send_mode
        return send_mode

    def _ensure_html_renderer(self) -> bool:
        if self._html_renderer is not None:
            return True
        try:
            template_path = Path(__file__).parent / "templates" / "main.html"
            self._html_renderer = HtmlCardRenderer(template_path)
            return True
        except (OSError, ValueError):
            logger.exception("html renderer initialize failed")
            return False

    def _is_group_blocked(self, event: AstrMessageEvent) -> bool:
        try:
            group_id = event.message_obj.group_id
            if group_id and self.config.is_group_blocked(str(group_id)):
                return True
        except AttributeError:
            logger.debug("failed to inspect group id for blocked check")
        return False

    def is_group_blocked(self, event: AstrMessageEvent) -> bool:
        """公开方法：检查群聊是否被屏蔽。"""
        return self._is_group_blocked(event)

    def determine_r18(self, content_mode: str) -> bool:
        """公开方法：根据内容模式确定是否为 R18。"""
        return self._determine_r18(content_mode)

    @property
    def session_config(self) -> SessionConfigManager:
        """公开属性：获取会话配置管理器。"""
        return self._session_config

    @property
    def config(self) -> SetuConfig:
        """公开属性：获取插件配置。"""
        return self._config

    def _get_bot_api(self, event: AstrMessageEvent) -> Any | None:
        """从事件中获取底层 bot API 客户端。"""
        return getattr(event, "bot", None)

    async def _revoke_message(
        self, event: AstrMessageEvent, message_id: str | int
    ) -> bool:
        """通过消息 ID 撤回消息。"""
        try:
            bot = self._get_bot_api(event)
            if not bot:
                logger.warning("[revoke] No bot instance available")
                return False

            # 尝试不同的参数格式以适应不同平台
            params_list = [
                {"message_id": message_id},
                {
                    "message_id": int(message_id)
                    if str(message_id).isdigit()
                    else message_id
                },
            ]

            for params in params_list:
                try:
                    await bot.call_action("delete_msg", **params)
                    logger.info("[revoke] Successfully revoked message %s", message_id)
                    return True
                except (RuntimeError, ConnectionError, TimeoutError) as exc:
                    logger.debug("[revoke] Failed with params %s: %s", params, exc)
                    continue

            logger.warning("[revoke] All attempts failed for message %s", message_id)
            return False
        except (RuntimeError, ConnectionError):
            logger.exception("[revoke] Error revoking message %s", message_id)
            return False

    async def _schedule_revoke(
        self, event: AstrMessageEvent, message_id: str | int, delay: int
    ) -> None:
        """调度消息在 delay 秒后撤回。"""
        if not message_id:
            return

        platform = event.get_platform_name()
        session_id = event.get_session_id()
        is_group = bool(event.get_group_id())
        revoke_time = int(time.time()) + delay

        # 获取 bot 引用以备后用
        bot = self._get_bot_api(event)
        bot_id = id(bot) if bot else None

        await self._revoke_manager.add_entry(
            str(message_id), platform, session_id, is_group, revoke_time
        )

        # 启动后台任务以在延迟后撤回
        # 存储必要信息而不是事件引用，并保存任务引用以便后续管理
        task = asyncio.create_task(
            self._delayed_revoke(
                str(message_id), delay, platform, session_id, is_group, bot_id, bot
            )
        )
        self._revoke_tasks.add(task)
        task.add_done_callback(self._revoke_tasks.discard)

    async def _delayed_revoke(
        self,
        message_id: str,
        delay: int,
        _platform: str,
        _session_id: str,
        _is_group: bool,
        bot_id: int | None,
        bot: Any | None,
    ) -> None:
        """后台任务：在 delay 秒后撤回消息。

        参数前缀为 _ 的表示在函数体内未直接使用，但保留以明确接口契约。
        """
        await asyncio.sleep(delay)

        # 尝试使用存储的 bot 引用进行撤回
        success = False
        if bot and bot_id:
            try:
                params_list = [
                    {"message_id": message_id},
                    {
                        "message_id": int(message_id)
                        if str(message_id).isdigit()
                        else message_id
                    },
                ]
                for params in params_list:
                    try:
                        await bot.call_action("delete_msg", **params)
                        success = True
                        break
                    except (RuntimeError, ConnectionError, TimeoutError):
                        continue
            except (RuntimeError, ConnectionError, TimeoutError) as exc:
                logger.warning("[revoke] Background revoke failed: %s", exc)

        if success:
            await self._revoke_manager.mark_revoked(message_id)
            logger.info("[revoke] Successfully revoked message %s", message_id)
        else:
            # 即使撤回失败，也标记为已处理，避免记录长期累积
            await self._revoke_manager.mark_revoked(message_id)
            logger.warning("[revoke] Failed to revoke message %s, marked as revoked", message_id)

    async def _send_with_revoke_support(
        self,
        event: AstrMessageEvent,
        chain: list[Any],
        is_group: bool,
        session_id: str,
    ) -> str | None:
        """发送消息并返回 message_id 以支持撤回。

        成功返回 message_id，否则返回 None。
        """
        try:
            bot = self._get_bot_api(event)
            if not bot:
                return None

            # 将链条解析为 OneBot 格式（如果可能）
            messages = []
            for comp in chain:
                if isinstance(comp, Comp.Plain):
                    if comp.text.strip():
                        messages.append({"type": "text", "data": {"text": comp.text}})
                elif isinstance(comp, Comp.Image):
                    # 处理图片 - 如果需要，转换为 base64
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

            # 根据消息类型调用发送 API
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

            # 从结果中提取 message_id
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
        self,
        event: AstrMessageEvent,
        file_path: str,
        file_name: str,
    ) -> str | None:
        """以消息形式发送文件并返回 message_id 以支持撤回。

        注意：使用 send_group_msg/send_private_msg 携带 file 段而不是
        upload_group_file，这样我们可以获得 message_id 以便撤回。
        如果文件过大（>5MB）则回退为普通文件发送。
        """
        try:
            bot = self._get_bot_api(event)
            if not bot:
                return None

            is_group = bool(event.get_group_id())
            session_id = event.get_group_id() or event.get_sender_id()

            # 检查文件大小
            path_obj = Path(file_path)
            file_size = path_obj.stat().st_size
            max_size = 5 * 1024 * 1024  # 5MB 的 base64 限制

            if file_size > max_size:
                logger.warning(
                    "[revoke] File too large (%d bytes > %d), cannot use revoke support",
                    file_size,
                    max_size,
                )
                return None

            # 将文件转换为 base64 以便作为消息发送
            import base64

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

            # 提取结果中的 message_id
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
        self,
        event: AstrMessageEvent,
        nodes: list[Comp.Node],
    ) -> str | None:
        """发送合并转发消息并返回 message_id 以支持撤回。"""
        try:
            bot = self._get_bot_api(event)
            if not bot:
                return None

            is_group = bool(event.get_group_id())
            session_id = event.get_group_id() or event.get_sender_id()

            # 将节点转换为字典格式
            messages = []
            for node in nodes:
                node_dict = await node.to_dict()
                messages.append(node_dict)

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

            # 提取结果中的 message_id
            if isinstance(result, dict):
                data = result.get("data", result)
                message_id = data.get("message_id") if isinstance(data, dict) else None
                if message_id:
                    return str(message_id)
            return None
        except (OSError, RuntimeError):
            logger.exception("[revoke] Failed to send nodes with revoke support")
            return None

    async def fetch_and_download_images(
        self, num: int, tags: list[str], is_r18: bool
    ) -> list[bytes]:
        provider = None
        try:
            provider = self._get_provider()
        except (ValueError, RuntimeError):
            logger.exception("provider initialization failed")
            return []

        if not provider:
            logger.error("no provider available")
            return []

        exclude_ai = self.config.exclude_ai
        max_replenish = self.config.max_replenish_rounds

        try:
            img_urls = await provider.fetch_image_urls(
                num=num,
                tags=tags,
                r18=is_r18,
                exclude_ai=exclude_ai,
            )
        except (RuntimeError, ConnectionError, TimeoutError) as exc:
            logger.error("provider fetch failed: %s", exc)
            return []

        if not img_urls:
            logger.info("provider returned empty urls")
            return []

        if not self._image_service:
            logger.error("image service unavailable")
            return []

        downloaded = await self._image_service.download_parallel(img_urls)
        logger.info(
            "initial download target=%d success=%d failed=%d",
            num,
            len(downloaded),
            max(0, num - len(downloaded)),
        )

        round_num = 0
        while len(downloaded) < num and round_num < max_replenish:
            missing = num - len(downloaded)
            logger.info(
                "replenish round %d/%d missing=%d",
                round_num + 1,
                max_replenish,
                missing,
            )
            try:
                extra_urls = await provider.fetch_image_urls(
                    num=missing,
                    tags=tags,
                    r18=is_r18,
                    exclude_ai=exclude_ai,
                )
                if extra_urls:
                    extra_downloaded = await self._image_service.download_parallel(
                        extra_urls
                    )
                    downloaded.extend(extra_downloaded)
            except Exception as exc:
                logger.warning("replenish round %d failed: %s", round_num + 1, exc)
            round_num += 1
        return downloaded

    async def send_images(
        self,
        event: AstrMessageEvent,
        images: list[bytes],
        is_r18: bool,
        tags: list[str] | None = None,
    ) -> AsyncGenerator[Any, None]:
        if not images:
            yield event.plain_result("运气不好，一张图都没拿到...")
            return

        cfg = self.config
        send_mode = cfg.send_mode
        enable_html_card = cfg.enable_html_card and self._html_renderer is not None
        auto_revoke = is_r18 and cfg.auto_revoke_r18

        actual_send_mode = self._resolve_send_mode(send_mode, len(images))

        # 处理 R18 docx 模式和自动撤回支持
        if is_r18 and cfg.r18_docx_mode:
            logger.info("[r18] use docx wrapper")
            docx_path = self._docx_service.create_docx_with_images(images, tags=tags)
            if docx_path:
                if auto_revoke:
                    # 直接发送文件以获取 message_id
                    # 使用来自 docx_path 的实际文件名
                    actual_filename = docx_path.name
                    message_id = await self._send_file_with_revoke(
                        event, str(docx_path), actual_filename
                    )
                    if message_id:
                        await self._schedule_revoke(
                            event, message_id, cfg.auto_revoke_delay
                        )
                        if cfg.msg_found_enabled:
                            yield event.plain_result(
                                f"{cfg.format_found_message(len(images))}（将在 {cfg.auto_revoke_delay} 秒后自动撤回）"
                            )
                        logger.info(
                            "[r18] Scheduled docx revoke in %ds, message_id=%s",
                            cfg.auto_revoke_delay,
                            message_id,
                        )
                    else:
                        # 如果撤回设置失败（例如，文件太大），则回退到正常文件发送
                        if cfg.msg_found_enabled:
                            yield event.plain_result(
                                cfg.format_found_message(len(images))
                            )
                        # 使用来自 docx_path 的实际文件名
                        actual_filename = docx_path.name
                        yield event.chain_result(
                            [Comp.File(file=str(docx_path), name=actual_filename)]
                        )
                else:
                    if cfg.msg_found_enabled:
                        yield event.plain_result(cfg.format_found_message(len(images)))
                    # 使用来自 docx_path 的实际文件名
                    actual_filename = docx_path.name
                    yield event.chain_result(
                        [Comp.File(file=str(docx_path), name=actual_filename)]
                    )
                return
            # Docx 生成失败
            logger.warning("[r18] docx wrapping failed")
            yield event.plain_result("R18 Docx 封装失败，请稍后再试或联系管理员。")
            return

        if enable_html_card:
            try:
                async for result in self._send_with_html_card(
                    event, images, actual_send_mode, auto_revoke
                ):
                    yield result
                return
            except (RuntimeError, ValueError, ConnectionError):
                logger.exception("html card send failed, fallback to regular send")

        async for result in self._send_images_fallback(
            event, images, actual_send_mode, auto_revoke
        ):
            yield result

    async def _send_with_html_card(
        self,
        event: AstrMessageEvent,
        images: list[bytes],
        send_mode: str,
        auto_revoke: bool = False,
    ) -> AsyncGenerator[Any, None]:
        cfg = self.config
        html_card_mode = cfg.html_card_mode
        logger.info("[html-card] mode=%s auto_revoke=%s", html_card_mode, auto_revoke)

        if not self._html_renderer:
            logger.warning("html renderer unavailable")
            async for result in self._send_images_fallback(
                event, images, send_mode, auto_revoke
            ):
                yield result
            return

        render_style = {
            "card_padding": cfg.html_card_padding,
            "card_gap": cfg.html_card_gap,
        }

        if html_card_mode == "multiple":
            html_image_urls: list[str] = []
            for img_data in images:
                image_url = await self._html_renderer.render_single_image(
                    context=self.plugin,
                    image=img_data,
                    style_options=render_style,
                )
                if image_url:
                    html_image_urls.append(image_url)

            if html_image_urls:
                nodes = []
                for img_url in html_image_urls:
                    node = Comp.Node(
                        uin=event.get_self_id(),
                        name="色图",
                        content=[Comp.Image.fromURL(img_url)],
                    )
                    nodes.append(node)

                if auto_revoke:
                    # 对于转发消息，我们需要发送并获取 message_id
                    message_id = await self._send_nodes_with_revoke(event, nodes)
                    if message_id:
                        await self._schedule_revoke(
                            event, message_id, cfg.auto_revoke_delay
                        )
                        # 发送合并通知和找到的消息
                        if cfg.msg_found_enabled:
                            notice = f"{cfg.format_found_message(len(html_image_urls))}\n将在 {cfg.auto_revoke_delay} 秒后自动撤回~"
                            yield event.plain_result(notice)
                        logger.info(
                            "[r18] Scheduled forward revoke in %ds, message_id=%s",
                            cfg.auto_revoke_delay,
                            message_id,
                        )
                    else:
                        # 回退到正常发送
                        if cfg.msg_found_enabled:
                            yield event.plain_result(
                                cfg.format_found_message(len(html_image_urls))
                            )
                        yield event.chain_result([Comp.Nodes(nodes)])
                else:
                    if cfg.msg_found_enabled:
                        yield event.plain_result(
                            cfg.format_found_message(len(html_image_urls))
                        )
                    yield event.chain_result([Comp.Nodes(nodes)])
                return

            yield event.plain_result("图片包装失败，尝试直接发送...")
            async for result in self._send_images_fallback(
                event, images, send_mode, auto_revoke
            ):
                yield result
            return

        image_url = await self._html_renderer.render_images(
            context=self.plugin,
            images=images,
            style_options=render_style,
        )
        if image_url:
            if auto_revoke:
                # 直接发送以获取 message_id
                chain = [Comp.Image.fromURL(image_url)]
                if send_mode == "forward":
                    node = Comp.Node(
                        uin=event.get_self_id(),
                        name="色图",
                        content=chain,
                    )
                    message_id = await self._send_nodes_with_revoke(event, [node])
                else:
                    message_id = await self._send_with_revoke_support(
                        event,
                        chain,
                        bool(event.get_group_id()),
                        event.get_group_id() or event.get_sender_id(),
                    )
                if message_id:
                    await self._schedule_revoke(
                        event, message_id, cfg.auto_revoke_delay
                    )
                    # 发送合并通知和找到的消息
                    if cfg.msg_found_enabled:
                        notice = f"{cfg.format_found_message(len(images))}\n将在 {cfg.auto_revoke_delay} 秒后自动撤回~"
                        yield event.plain_result(notice)
                    logger.info(
                        "[r18] Scheduled html-card revoke in %ds, message_id=%s",
                        cfg.auto_revoke_delay,
                        message_id,
                    )
                else:
                    # 回退：使用正常发送
                    if cfg.msg_found_enabled:
                        yield event.plain_result(cfg.format_found_message(len(images)))
                    if send_mode == "forward":
                        node = Comp.Node(
                            uin=event.get_self_id(),
                            name="色图",
                            content=[Comp.Image.fromURL(image_url)],
                        )
                        yield event.chain_result([Comp.Nodes([node])])
                    else:
                        yield event.image_result(image_url)
            else:
                if cfg.msg_found_enabled:
                    yield event.plain_result(cfg.format_found_message(len(images)))
                if send_mode == "forward":
                    node = Comp.Node(
                        uin=event.get_self_id(),
                        name="色图",
                        content=[Comp.Image.fromURL(image_url)],
                    )
                    yield event.chain_result([Comp.Nodes([node])])
                else:
                    yield event.image_result(image_url)
            return

        yield event.plain_result("图片包装失败，尝试直接发送...")
        async for result in self._send_images_fallback(
            event, images, send_mode, auto_revoke
        ):
            yield result

    async def _send_images_fallback(
        self,
        event: AstrMessageEvent,
        images: list[bytes],
        send_mode: str,
        auto_revoke: bool = False,
    ) -> AsyncGenerator[Any, None]:
        if not self._image_service:
            logger.error("image service unavailable in fallback")
            yield event.plain_result("插件内部错误：图片服务不可用。")
            return
        cfg = self.config
        found_message = (
            cfg.format_found_message(len(images)) if cfg.msg_found_enabled else None
        )

        if auto_revoke:
            # 对于自动撤回，我们需要直接发送以获取 message_id
            if send_mode == "forward":
                nodes = []
                for img_data in images:
                    node = Comp.Node(
                        uin=event.get_self_id(),
                        name="色图",
                        content=[Comp.Image.fromBytes(img_data)],
                    )
                    nodes.append(node)
                message_id = await self._send_nodes_with_revoke(event, nodes)
            else:
                # 带有找到的消息发送图片
                chain: list[Any] = []
                if found_message:
                    chain.append(Comp.Plain(found_message))
                for img_data in images:
                    chain.append(Comp.Image.fromBytes(img_data))
                message_id = await self._send_with_revoke_support(
                    event,
                    chain,
                    bool(event.get_group_id()),
                    event.get_group_id() or event.get_sender_id(),
                )

            if message_id:
                await self._schedule_revoke(event, message_id, cfg.auto_revoke_delay)
                # 发送撤回通知
                notice = f"R18 内容已发送，将在 {cfg.auto_revoke_delay} 秒后自动撤回~"
                yield event.plain_result(notice)
                logger.info(
                    "[r18] Scheduled fallback revoke in %ds, message_id=%s",
                    cfg.auto_revoke_delay,
                    message_id,
                )
            else:
                logger.warning("[r18] Failed to get message_id for revoke, using yield")
                if send_mode == "forward":
                    async for result in self._image_service.send_forward(
                        event, images, "色图"
                    ):
                        yield result
                else:
                    async for result in self._image_service.send_images(
                        event, images, found_message
                    ):
                        yield result
        else:
            if send_mode == "forward":
                async for result in self._image_service.send_forward(
                    event, images, "色图"
                ):
                    yield result
            else:
                async for result in self._image_service.send_images(
                    event, images, found_message
                ):
                    yield result

    async def _send_event_result_to_origin(
        self, event: AstrMessageEvent, result: Any
    ) -> None:
        from astrbot.api.event import MessageChain

        chain = getattr(result, "chain", None) or []
        await self.plugin.context.send_message(
            event.unified_msg_origin, MessageChain(chain)
        )

    async def _send_generator_results_to_origin(
        self, event: AstrMessageEvent, generator: AsyncGenerator[Any, None]
    ) -> tuple[int, int]:
        sent_count = 0
        media_count = 0
        async for result in generator:
            chain = getattr(result, "chain", None) or []
            await self._send_event_result_to_origin(event, result)
            sent_count += 1
            if any(
                isinstance(
                    comp,
                    (Comp.Image, Comp.File, Comp.Node, Comp.Nodes),
                )
                for comp in chain
            ):
                media_count += 1
        return sent_count, media_count

    async def _send_llm_error_message(self, event: AstrMessageEvent) -> None:
        from astrbot.api.event import MessageChain

        await self.plugin.context.send_message(
            event.unified_msg_origin,
            MessageChain([Comp.Plain(self.config.msg_send_failed_text)]),
        )

    async def _try_llm_html_fallback_send(
        self, event: AstrMessageEvent, images: list[bytes], send_mode: str
    ) -> bool:
        if not self._ensure_html_renderer():
            return False
        try:
            _, media_count = await self._send_generator_results_to_origin(
                event, self._send_with_html_card(event, images, send_mode)
            )
            return media_count > 0
        except (RuntimeError, ConnectionError, TimeoutError) as exc:
            logger.warning("llm html fallback send failed: %s", exc)
            return False

    async def handle_llm_tool(
        self, event: AstrMessageEvent, count: int, tags: list[str] | str | None
    ) -> tuple[bool, str]:
        cfg = self.config
        if self._is_group_blocked(event):
            return False, "该群聊已禁用此功能。"

        try:
            num = max(1, min(int(count), cfg.max_count))
        except (ValueError, TypeError):
            num = 1
        if isinstance(tags, list):
            normalized_tags = [str(t).strip() for t in tags if str(t).strip()]
            parsed_tags: list[str] = []
            for tag in normalized_tags:
                parsed_tags.extend(cfg.resolve_tags(tag))
        else:
            parsed_tags = cfg.resolve_tags(str(tags or ""))

        # 获取生效的内容模式（优先会话配置）
        effective_content_mode = await self.get_effective_content_mode(event)
        is_r18 = self._determine_r18(effective_content_mode)
        downloaded = await self.fetch_and_download_images(num, parsed_tags, is_r18)
        if not downloaded:
            return False, "未能获取到图片或图片下载失败。"

        actual_send_mode = self._resolve_send_mode(cfg.send_mode, len(downloaded))
        try:
            _, media_count = await self._send_generator_results_to_origin(
                event, self.send_images(event, downloaded, is_r18, parsed_tags)
            )
            if media_count > 0:
                return True, f"已成功发送 {len(downloaded)} 张图片"
        except (RuntimeError, ConnectionError, TimeoutError) as exc:
            logger.warning("llm primary send failed: %s", exc)

        if cfg.auto_handle_send_failure:
            html_sent = await self._try_llm_html_fallback_send(
                event, downloaded, actual_send_mode
            )
            if html_sent:
                return True, f"已发送 {len(downloaded)} 张图片（自动HTML降级）"

        try:
            await self._send_llm_error_message(event)
        except Exception as notify_exc:
            logger.warning("llm send-failed notice failed: %s", notify_exc)
        return False, cfg.msg_send_failed_text
