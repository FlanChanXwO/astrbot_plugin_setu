"""HTML 卡片渲染服务，用于将图片包装成防审核的卡片样式。"""

from __future__ import annotations

import base64
import random
from pathlib import Path
from typing import Any

import aiohttp

from astrbot.api import logger
from .constants import HTTP_TIMEOUT_SECONDS


class HtmlCardRenderer:
    """HTML 卡片渲染器，用于包装图片以规避平台审核。"""

    # 随机背景色选项（低对比度柔和色系）
    BG_COLORS = [
        "#f0f2f5", "#f5f0f0", "#f0f5f2", "#f2f0f5",
        "#faf8f5", "#f5f8fa", "#f8f5fa", "#f5faf8",
        "#fff5f0", "#f0fff5", "#f5f0ff", "#fffff0",
    ]

    # 卡片边框颜色选项
    BORDER_COLORS = [
        "#e0e2e5", "#e5e0e0", "#e0e5e2", "#e2e0e5",
        "#d0d2d5", "#d5d0d0", "#d0d5d2", "#d2d0d5",
    ]

    # 旋转角度范围（度）
    ROTATION_RANGE = (-2.0, 2.0)

    def __init__(self, template_path: Path | None = None):
        self.template_path = template_path or Path(__file__).parent / "templates" / "main.html"
        self._template = None

    def _load_template(self) -> str:
        """加载 HTML 模板。"""
        if self._template is None:
            self._template = self.template_path.read_text(encoding="utf-8")
        return self._template

    def _generate_random_styles(self) -> dict[str, Any]:
        """生成随机样式参数。"""
        return {
            "bg_color": random.choice(self.BG_COLORS),
            "card_bg": "#ffffff",
            "border_color": random.choice(self.BORDER_COLORS),
            "rotation": random.uniform(*self.ROTATION_RANGE),
            "noise_opacity": random.uniform(0.05, 0.12),
            "grid_opacity": random.uniform(0.02, 0.05),
            "border_radius": random.randint(8, 16),
            "padding": random.randint(8, 16),
        }

    def _build_html(self, images_b64: list[str]) -> str:
        """构建包含图片的 HTML 内容。"""
        template = self._load_template()
        styles = self._generate_random_styles()

        # 为每张图片生成卡片 - 紧凑样式
        cards_html = []
        for i, img_b64 in enumerate(images_b64):
            card_rotation = styles["rotation"] + random.uniform(-0.5, 0.5)
            # 减少内边距和间距，使卡片更紧凑
            card_style = f"""
                background: {styles['card_bg']};
                border-radius: {styles['border_radius']}px;
                padding: 6px;
                margin-bottom: 8px;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
                transform: rotate({card_rotation:.2f}deg);
                border: 1px solid {styles['border_color']};
                display: inline-block;
            """

            cards_html.append(f"""
        <div class="image-card" style="{card_style}">
            <div class="grid-overlay"></div>
            <img src="data:image/png;base64,{img_b64}" class="safe-img" alt="img{i+1}" loading="eager">
        </div>
            """)

        # 生成随机背景样式 - 减少padding
        body_style = f"""
            margin: 0;
            padding: 8px;
            background-color: {styles['bg_color']};
            font-family: system-ui, -apple-system, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
        """

        # 替换模板中的占位符
        html = template.replace(
            "{cards}", "\n".join(cards_html)
        ).replace(
            "{body_style}", body_style
        ).replace(
            "{noise_opacity}", str(styles["noise_opacity"])
        ).replace(
            "{grid_opacity}", str(styles["grid_opacity"])
        )

        return html

    async def render_single_image(
        self,
        context,
        image: bytes,
    ) -> str | None:
        """将单张图片渲染为 HTML 卡片。

        参数:
            context: AstrBot 的 Star 上下文，用于调用 html_render
            image: 图片字节数据

        返回:
            渲染后的图片 URL，失败返回 None
        """
        if not image or not context:
            return None

        try:
            # 将图片转换为 base64
            img_b64 = base64.b64encode(image).decode("ascii")

            # 构建单张图片的 HTML
            html_content = self._build_html([img_b64])

            # 使用 AstrBot 的 html_render 渲染
            render_options = {
                "full_page": True,
                "type": "png",
            }

            image_url = await context.html_render(
                tmpl=html_content,
                data={},
                return_url=True,
                options=render_options,
            )

            return image_url

        except Exception as e:
            logger.error("HTML 单张卡片渲染失败: %s", e)
            return None

    async def render_images(
        self,
        context,
        images: list[bytes],
        options: dict[str, Any] | None = None,
    ) -> str | None:
        """将图片渲染为 HTML 卡片并截图。

        参数:
            context: AstrBot 的 Star 上下文，用于调用 html_render
            images: 图片字节数据列表
            options: 渲染选项

        返回:
            渲染后的图片 URL，失败返回 None
        """
        if not images or not context:
            return None

        try:
            # 将图片转换为 base64
            images_b64 = [base64.b64encode(img).decode("ascii") for img in images]

            # 构建 HTML
            html_content = self._build_html(images_b64)

            # 使用 AstrBot 的 html_render 渲染
            # 使用 PNG 格式获得无损压缩，避免默认 JPEG quality=40 导致的严重压缩
            render_options = {
                "full_page": True,
                "type": "png",
            }

            image_url = await context.html_render(
                tmpl=html_content,
                data={},
                return_url=True,
                options=render_options,
            )

            return image_url

        except Exception as e:
            logger.error("HTML 卡片渲染失败: %s", e)
            return None

    def render_to_html_file(
        self,
        images: list[bytes],
        output_path: Path,
    ) -> bool:
        """将图片渲染为 HTML 文件（用于调试）。

        参数:
            images: 图片字节数据列表
            output_path: 输出 HTML 文件路径

        返回:
            是否成功
        """
        try:
            images_b64 = [base64.b64encode(img).decode("ascii") for img in images]
            html_content = self._build_html(images_b64)
            output_path.write_text(html_content, encoding="utf-8")
            return True
        except Exception as e:
            logger.error("HTML 文件保存失败: %s", e)
            return False
