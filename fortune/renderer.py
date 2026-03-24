"""今日运势 HTML 渲染模块。"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from astrbot.api import logger


class FortuneRenderer:
    """运势卡片渲染器。"""

    def __init__(self, template_path: Path | None = None):
        if template_path is None:
            template_path = Path(__file__).parent.parent / "templates" / "fortune.html"
        self.template_path = template_path
        self._fonts_dir = self.template_path.parent / "res" / "fonts"
        self._embedded_fonts_css: str | None = None

    def _get_embedded_fonts_css(self) -> str:
        """生成内嵌字体的 CSS（使用 base64）。

        字体文件会被缓存，避免重复读取。
        """
        if self._embedded_fonts_css is not None:
            return self._embedded_fonts_css

        fonts_config = [
            {
                "name": "NotoSansSC-Regular",
                "file": "NotoSansSC-Regular.otf",
                "format": "opentype",
                "mime": "font/otf",
            },
            {
                "name": "NotoSansSC-Bold",
                "file": "NotoSansSC-Bold.otf",
                "format": "opentype",
                "mime": "font/otf",
            },
            {
                "name": "SSFangTangTi",
                "file": "SSFangTangTi.ttf",
                "format": "truetype",
                "mime": "font/truetype",
            },
        ]

        css_parts = ["    /* Embedded fonts - auto-generated */"]

        for font in fonts_config:
            font_path = self._fonts_dir / font["file"]
            try:
                if font_path.exists():
                    font_data = font_path.read_bytes()
                    b64_data = base64.b64encode(font_data).decode("ascii")
                    css_parts.append(f"""    @font-face {{
      font-family: '{font["name"]}';
      src: url('data:{font["mime"]};base64,{b64_data}') format('{font["format"]}');
      font-weight: normal;
      font-style: normal;
      font-display: swap;
    }}""")
                else:
                    logger.warning("[fortune] Font file not found: %s", font_path)
            except OSError as exc:
                logger.error("[fortune] Failed to read font %s: %s", font["file"], exc)

        self._embedded_fonts_css = "\n".join(css_parts)
        return self._embedded_fonts_css

    @staticmethod
    def _truncate_username(username: str, max_length: int = 15) -> str:
        """截断用户名，超过最大长度时用...省略。

        参数:
            username: 原始用户名
            max_length: 最大字符数，默认15

        返回:
            截断后的用户名
        """
        if len(username) > max_length:
            return username[:max_length] + "..."
        return username

    def _get_template(self) -> str:
        try:
            return self.template_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error("[fortune] Failed to read template: %s", exc)
            # 返回一个极简的备用模板
            return """<!DOCTYPE html>
<html><body style="width:480px;padding:20px;">
<div style="background:#f0f0f0;border-radius:10px;padding:20px;">
<h2>{{ username }} 的今日运势 ({{ date_str }})</h2>
<p>运势: {{ title }}</p>
<p>星级: {{ stars_display }}</p>
<p>{{ description }}</p>
</div></body></html>"""

    def render(self, fortune: dict[str, Any], image_base64: str | None = None) -> str:
        """渲染运势卡片为 HTML 字符串。

        参数:
            fortune: 运势数据
            image_base64: 背景图片的 base64 编码（可选）

        返回:
            HTML 字符串（包含内嵌字体，适用于 Playwright 截图）
        """
        template = self._get_template()

        # 构建渲染数据（包含内嵌字体 CSS）
        username = self._truncate_username(fortune.get("username", "用户"))
        data = {
            "fonts_css": self._get_embedded_fonts_css(),
            "username": username,
            "date_str": fortune.get("date_str", ""),
            "title": fortune.get("title", "未知"),
            "stars_display": self._format_stars(
                fortune.get("star_count", 3), fortune.get("max_stars", 7)
            ),
            "description": fortune.get("description", ""),
            "extra_message": fortune.get("extra_message", ""),
            "theme_color": fortune.get("theme_color", "theme-gray"),
            "image_base64": image_base64 or "",
        }

        # 简单的模板渲染（替换 {{ variable }}）
        html = template
        for key, value in data.items():
            placeholder = f"{{{{ {key} }}}}"
            html = html.replace(placeholder, str(value))

        # 处理条件语句 {% if variable %}...{% endif %}
        import re

        # 处理 if 语句
        def process_if(match: re.Match) -> str:
            condition = match.group(1).strip()
            content = match.group(2)
            # 检查条件是否为真（变量存在且非空）
            if condition in data and data[condition]:
                return content
            return ""

        html = re.sub(
            r"{%\s*if\s+(\w+)\s*%}(.*?){%\s*endif\s*%}",
            process_if,
            html,
            flags=re.DOTALL,
        )

        return html

    def _format_stars(self, count: int, max_count: int = 7) -> str:
        """格式化星级显示为HTML。"""
        stars_html = []
        # 填充的星星
        for _ in range(count):
            stars_html.append('<span class="star">★</span>')
        # 空星星
        for _ in range(max_count - count):
            stars_html.append('<span class="star empty">★</span>')
        return "".join(stars_html)

    async def render_to_image(
        self,
        fortune: dict[str, Any],
        image_base64: str | None = None,
        html_renderer=None,
    ) -> bytes | None:
        """渲染运势卡片为图片。

        使用 AstrBot 的 T2I 服务（Jinja2 模板引擎）。

        参数:
            fortune: 运势数据
            image_base64: 背景图片 base64
            html_renderer: HTML 渲染器（AstrBot context 的 html_render 方法）

        返回:
            图片字节数据，失败返回 None
        """
        if html_renderer is None:
            logger.error("[fortune] No HTML renderer available")
            return None

        try:
            # 读取 HTML 模板（使用 Jinja2 语法）
            template = self._get_template()

            # 准备模板数据（通过 data 参数传递给 Jinja2，包含内嵌字体 CSS）
            username = self._truncate_username(fortune.get("username", "用户"))
            tmpl_data = {
                "fonts_css": self._get_embedded_fonts_css(),
                "username": username,
                "date_str": fortune.get("date_str", ""),
                "title": fortune.get("title", "未知"),
                "stars_display": self._format_stars(
                    fortune.get("star_count", 3), fortune.get("max_stars", 7)
                ),
                "description": fortune.get("description", ""),
                "extra_message": fortune.get("extra_message", ""),
                "theme_color": fortune.get("theme_color", "theme-gray"),
                "image_base64": image_base64 or "",
            }

            # 使用 AstrBot 的 html_render 方法
            # 参考 Playwright screenshot API: https://playwright.dev/python/docs/api/class-page#page-screenshot
            render_options = {
                "full_page": True,
                "type": "png",
                "scale": "device",
            }
            result = await html_renderer(
                tmpl=template, data=tmpl_data, return_url=False, options=render_options
            )

            # 处理返回值（可能是文件路径字符串）
            if result is None:
                logger.error("[fortune] html_render returned None")
                return None

            if isinstance(result, str):
                # 结果是文件路径
                import asyncio
                from pathlib import Path

                path = Path(result)
                if path.exists():
                    # 检查文件大小
                    file_size = path.stat().st_size
                    logger.debug(
                        "[fortune] Reading image from path: %s (%d bytes)",
                        result,
                        file_size,
                    )
                    if file_size < 100:
                        logger.error(
                            "[fortune] Rendered image too small (%d bytes), likely failed",
                            file_size,
                        )
                        return None
                    return await asyncio.to_thread(path.read_bytes)
                else:
                    logger.error("[fortune] Rendered file not found: %s", result)
                    return None

            logger.error(
                "[fortune] Unexpected return type from html_render: %s", type(result)
            )
            return None

        except NotImplementedError:
            logger.error(
                "[fortune] HTML rendering not supported by current T2I strategy (local strategy doesn't support custom templates)"
            )
            return None
        except Exception as exc:
            logger.exception("[fortune] Failed to render image: %s", exc)
            return None
