"""HTML card renderer for safer image wrapping."""

from __future__ import annotations

import base64
import random
from pathlib import Path
from typing import Any

from astrbot.api import logger


class HtmlCardRenderer:
    """Wrap image(s) into compact HTML cards then render with AstrBot html_render."""

    BG_COLORS = [
        "#f0f2f5",
        "#f5f0f0",
        "#f0f5f2",
        "#f2f0f5",
        "#faf8f5",
        "#f5f8fa",
        "#f8f5fa",
        "#f5faf8",
        "#fff5f0",
        "#f0fff5",
        "#f5f0ff",
        "#fffff0",
    ]
    BORDER_COLORS = [
        "#e0e2e5",
        "#e5e0e0",
        "#e0e5e2",
        "#e2e0e5",
        "#d0d2d5",
        "#d5d0d0",
        "#d0d5d2",
        "#d2d0d5",
    ]
    ROTATION_RANGE = (-2.0, 2.0)

    def __init__(self, template_path: Path | None = None):
        self.template_path = (
            template_path or Path(__file__).parent / "templates" / "main.html"
        )
        self._template: str | None = None

    def _load_template(self) -> str:
        if self._template is None:
            self._template = self.template_path.read_text(encoding="utf-8")
        return self._template

    def _generate_random_styles(
        self, style_options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        style_options = style_options or {}
        card_padding = int(style_options.get("card_padding", 6))
        card_gap = int(style_options.get("card_gap", 6))
        return {
            "bg_color": random.choice(self.BG_COLORS),
            "card_bg": "#ffffff",
            "border_color": random.choice(self.BORDER_COLORS),
            "rotation": random.uniform(*self.ROTATION_RANGE),
            "noise_opacity": random.uniform(0.04, 0.10),
            "grid_opacity": random.uniform(0.01, 0.04),
            "border_radius": random.randint(8, 14),
            "card_padding": max(2, card_padding),
            "card_gap": max(2, card_gap),
            "page_padding": 4,
        }

    def _build_html(
        self, images_b64: list[str], style_options: dict[str, Any] | None = None
    ) -> str:
        template = self._load_template()
        styles = self._generate_random_styles(style_options)

        cards_html = []
        for index, img_b64 in enumerate(images_b64):
            card_rotation = styles["rotation"] + random.uniform(-0.4, 0.4)
            card_style = (
                f"background:{styles['card_bg']};"
                f"border-radius:{styles['border_radius']}px;"
                f"padding:{styles['card_padding']}px;"
                f"margin-bottom:{styles['card_gap']}px;"
                "box-shadow:0 1px 3px rgba(0,0,0,0.05);"
                f"transform:rotate({card_rotation:.2f}deg);"
                f"border:1px solid {styles['border_color']};"
                "display:inline-block;"
            )
            cards_html.append(
                f"""
        <div class="image-card" style="{card_style}">
            <div class="grid-overlay"></div>
            <img src="data:image/png;base64,{img_b64}" class="safe-img" alt="img{index + 1}" loading="eager">
        </div>
                """
            )

        body_style = (
            "margin:0;"
            f"padding:{styles['page_padding']}px;"
            f"background-color:{styles['bg_color']};"
            "font-family:system-ui,-apple-system,sans-serif;"
            "display:inline-block;"
        )
        html = (
            template.replace("{cards}", "\n".join(cards_html))
            .replace("{body_style}", body_style)
            .replace("{noise_opacity}", str(styles["noise_opacity"]))
            .replace("{grid_opacity}", str(styles["grid_opacity"]))
        )
        return html

    async def render_single_image(
        self, context, image: bytes, style_options: dict[str, Any] | None = None
    ) -> str | None:
        if not image or not context:
            return None
        try:
            img_b64 = base64.b64encode(image).decode("ascii")
            html_content = self._build_html([img_b64], style_options=style_options)
            render_options = {
                "full_page": True,
                "type": "png",
                "scale": "device",
            }
            return await context.html_render(
                tmpl=html_content,
                data={},
                return_url=True,
                options=render_options,
            )
        except Exception:
            logger.exception("html single-card render failed")
            return None

    async def render_images(
        self,
        context,
        images: list[bytes],
        options: dict[str, Any] | None = None,
        style_options: dict[str, Any] | None = None,
    ) -> str | None:
        if not images or not context:
            return None
        try:
            images_b64 = [base64.b64encode(img).decode("ascii") for img in images]
            html_content = self._build_html(images_b64, style_options=style_options)
            render_options = {"full_page": True, "type": "png", "scale": "device"}
            if options:
                render_options.update(options)
            return await context.html_render(
                tmpl=html_content,
                data={},
                return_url=True,
                options=render_options,
            )
        except Exception:
            logger.exception("html card render failed")
            return None

    def render_to_html_file(self, images: list[bytes], output_path: Path) -> bool:
        try:
            images_b64 = [base64.b64encode(img).decode("ascii") for img in images]
            output_path.write_text(self._build_html(images_b64), encoding="utf-8")
            return True
        except Exception:
            logger.exception("html debug file save failed")
            return False
