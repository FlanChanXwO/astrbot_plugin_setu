"""Setu 插件核心业务逻辑。"""

from __future__ import annotations

import random
from pathlib import Path
from typing import AsyncGenerator, Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
import astrbot.api.message_components as Comp

from .config import SetuConfig
from .constants import HTTP_TIMEOUT_SECONDS
from .docx_service import DocxService
from .html_renderer import HtmlCardRenderer
from .image_service import ImageService
from .providers import get_provider


class SetuCore:
    """Setu 插件核心业务逻辑处理器。"""

    def __init__(self, context, config: SetuConfig):
        """初始化核心处理器。

        参数:
            context: AstrBot 插件上下文
            config: 插件配置
        """
        self.context = context
        self.config = config
        self._image_service = ImageService()
        self._docx_service = DocxService()
        self._html_renderer: HtmlCardRenderer | None = None

        # 初始化 HTML 渲染器
        if config.enable_html_card:
            template_path = Path(__file__).parent / "templates" / "main.html"
            self._html_renderer = HtmlCardRenderer(template_path)

    def _get_provider(self):
        """获取图片提供商。"""
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
            custom_api_configs=cfg.custom_api_configs if cfg.api_type in ("custom", "all") else None,
            multi_api_strategy=cfg.multi_api_strategy,
            lolicon_config=lolicon_config,
        )

    def _determine_r18(self, content_mode: str) -> bool:
        """根据内容模式确定 R18 标志。"""
        if content_mode == "r18":
            return True
        if content_mode == "mix":
            return random.random() > 0.5
        return False

    def _is_group_blocked(self, event: AstrMessageEvent) -> bool:
        """检查当前群聊是否被屏蔽。"""
        try:
            group_id = event.message_obj.group_id
            if group_id and self.config.is_group_blocked(str(group_id)):
                return True
        except AttributeError:
            pass
        return False

    async def fetch_and_download_images(
        self,
        num: int,
        tags: list[str],
        is_r18: bool,
    ) -> list[bytes]:
        """获取并下载图片。

        参数:
            num: 请求图片数量
            tags: 标签列表
            is_r18: 是否为 R18 内容

        返回:
            下载成功的图片字节数据列表
        """
        provider = self._get_provider()
        exclude_ai = self.config.exclude_ai
        max_replenish = self.config.max_replenish_rounds

        # 阶段 1: 从提供商获取图片 URL
        try:
            img_urls = await provider.fetch_image_urls(
                num=num, tags=tags, r18=is_r18, exclude_ai=exclude_ai
            )
        except Exception as exc:
            logger.error("提供商获取失败: %s", exc)
            return []

        if not img_urls:
            return []

        # 阶段 2: 并发下载图片
        downloaded = await self._image_service.download_parallel(img_urls)
        logger.info("首次下载: 目标=%d, 成功=%d, 失败=%d", num, len(downloaded), num - len(downloaded))

        # 阶段 3: 智能补充（404 时重试）
        round_num = 0
        while len(downloaded) < num and round_num < max_replenish:
            missing = num - len(downloaded)
            logger.info("补充轮次 %d/%d, 缺少 %d 张图片", round_num + 1, max_replenish, missing)
            try:
                extra_urls = await provider.fetch_image_urls(
                    num=missing, tags=tags, r18=is_r18, exclude_ai=exclude_ai
                )
                if extra_urls:
                    extra_downloaded = await self._image_service.download_parallel(extra_urls)
                    downloaded.extend(extra_downloaded)
            except Exception as exc:
                logger.warning("补充轮次 %d 失败: %s", round_num + 1, exc)
            round_num += 1

        return downloaded

    async def send_images(
        self,
        event: AstrMessageEvent,
        images: list[bytes],
        is_r18: bool,
    ) -> AsyncGenerator[Any, None]:
        """发送图片。

        参数:
            event: 消息事件
            images: 图片字节数据列表
            is_r18: 是否为 R18 内容
        """
        if not images:
            yield event.plain_result("运气不好，一张图都没拿到...")
            return

        cfg = self.config
        send_mode = cfg.send_mode
        enable_html_card = cfg.enable_html_card and self._html_renderer

        # 确定实际发送模式
        actual_send_mode = send_mode
        if send_mode == "auto":
            actual_send_mode = "forward" if len(images) > 1 else "image"
            logger.info("[Auto模式] 图片数量=%d, 选择发送模式=%s", len(images), actual_send_mode)

        # R18 图片使用 Docx 封装（如果启用）
        if is_r18 and cfg.r18_docx_mode:
            logger.info("[R18模式] 使用 Docx 文件封装发送")
            docx_path = self._docx_service.create_docx_with_images(images)
            if docx_path:
                yield event.plain_result(f"找到 {len(images)} 张符合要求的图片~（已封装）")
                yield event.file_result(str(docx_path), "setu.docx")
            else:
                yield event.plain_result("Docx 封装失败，尝试直接发送...")
                async for result in self._send_images_fallback(event, images, actual_send_mode):
                    yield result
            return

        # HTML 卡片模式
        if enable_html_card:
            async for result in self._send_with_html_card(event, images, actual_send_mode):
                yield result
            return

        # 普通发送模式
        async for result in self._send_images_fallback(event, images, actual_send_mode):
            yield result

    async def _send_with_html_card(
        self,
        event: AstrMessageEvent,
        images: list[bytes],
        send_mode: str,
    ) -> AsyncGenerator[Any, None]:
        """使用 HTML 卡片发送图片。"""
        cfg = self.config
        html_card_mode = cfg.html_card_mode
        logger.info("[HTML卡片模式] 模式=%s", html_card_mode)

        if html_card_mode == "multiple":
            # 单图单卡片 + 合并转发模式
            html_image_urls: list[str] = []
            for img_data in images:
                image_url = await self._html_renderer.render_single_image(
                    context=self.context,
                    image=img_data,
                )
                if image_url:
                    html_image_urls.append(image_url)

            if html_image_urls:
                yield event.plain_result(f"找到 {len(html_image_urls)} 张符合要求的图片~")
                nodes = []
                for img_url in html_image_urls:
                    node = Comp.Node(
                        uin=event.get_self_id(),
                        name="色图",
                        content=[Comp.Image.fromURL(img_url)]
                    )
                    nodes.append(node)
                yield event.chain_result(nodes)
            else:
                yield event.plain_result("图片包装失败，尝试直接发送...")
                async for result in self._send_images_fallback(event, images, send_mode):
                    yield result
        else:
            # single 模式：多图合一
            image_url = await self._html_renderer.render_images(
                context=self.context,
                images=images,
            )
            if image_url:
                if send_mode == "forward":
                    node = Comp.Node(
                        uin=event.get_self_id(),
                        name="色图",
                        content=[Comp.Image.fromURL(image_url)]
                    )
                    yield event.chain_result([node])
                else:
                    yield event.image_result(image_url)
            else:
                yield event.plain_result("图片包装失败，尝试直接发送...")
                async for result in self._send_images_fallback(event, images, send_mode):
                    yield result

    async def _send_images_fallback(
        self,
        event: AstrMessageEvent,
        images: list[bytes],
        send_mode: str,
    ) -> AsyncGenerator[Any, None]:
        """图片发送降级处理。"""
        if send_mode == "forward":
            async for result in self._image_service.send_forward(event, images, "色图"):
                yield result
        else:
            async for result in self._image_service.send_images(event, images):
                yield result

    async def handle_llm_tool(
        self,
        event: AstrMessageEvent,
        count: int,
        tags: str,
    ) -> tuple[bool, str]:
        """处理 LLM 工具调用。

        参数:
            event: 消息事件
            count: 图片数量
            tags: 标签字符串

        返回:
            (是否成功, 结果消息)
        """
        cfg = self.config

        # 检查群聊是否被屏蔽
        if self._is_group_blocked(event):
            return False, "该群聊已禁用此功能。"

        # 限制数量
        num = max(1, min(int(count), cfg.max_count))

        # 解析标签
        parsed_tags = cfg.resolve_tags(tags)

        # 获取图片
        is_r18 = self._determine_r18(cfg.content_mode)
        downloaded = await self.fetch_and_download_images(num, parsed_tags, is_r18)

        if not downloaded:
            return False, "未能获取到图片或图片下载失败。"

        # R18 图片使用 Docx 封装
        if is_r18 and cfg.r18_docx_mode:
            logger.info("[LLM工具][R18模式] 使用 Docx 文件封装发送")
            docx_path = self._docx_service.create_docx_with_images(downloaded)
            if docx_path:
                from astrbot.api.message_components import File
                from astrbot.api.event import MessageChain
                await self.context.send_message(
                    event.unified_msg_origin,
                    MessageChain([File(file=str(docx_path), name="setu.docx")])
                )
                return True, f"已发送 {len(downloaded)} 张图片（Docx封装）"
            else:
                logger.warning("[LLM工具] Docx 封装失败，降级为直接发送")

        # HTML 卡片模式
        if cfg.enable_html_card and self._html_renderer:
            if cfg.html_card_mode == "multiple" and len(downloaded) > 1:
                html_image_urls: list[str] = []
                for img_data in downloaded:
                    image_url = await self._html_renderer.render_single_image(
                        context=self.context,
                        image=img_data,
                    )
                    if image_url:
                        html_image_urls.append(image_url)

                if html_image_urls:
                    from astrbot.api.event import MessageChain
                    message_chain = []
                    for img_url in html_image_urls:
                        message_chain.append(Comp.Image.fromURL(img_url))
                    await self.context.send_message(event.unified_msg_origin, MessageChain(message_chain))
                    return True, f"已发送 {len(html_image_urls)} 张图片（HTML单卡包装）"
            else:
                image_url = await self._html_renderer.render_images(
                    context=self.context,
                    images=downloaded,
                )
                if image_url:
                    from astrbot.api.event import MessageChain
                    await self.context.send_message(
                        event.unified_msg_origin,
                        MessageChain.url_image(image_url)
                    )
                    return True, f"已发送 {len(downloaded)} 张图片（HTML卡片包装）"

        # 直接发送
        from astrbot.api.event import MessageChain
        message_chain = []
        for img_data in downloaded:
            message_chain.append(Comp.Image.fromBytes(img_data))

        await self.context.send_message(event.unified_msg_origin, MessageChain(message_chain))
        return True, f"已成功发送 {len(downloaded)} 张图片"
