"""Best-effort image compression before adapter-level sending.

setu image sources (especially original-size Pixiv mirrors) frequently return
very large images. A single oversized image inflates the base64 payload that
the OneBot adapter inlines into one WebSocket frame, and the aggregate can hit
the ~50 MiB single-frame ceiling on the AstrBot -> NapCat link. Shrinking each
image toward a byte budget keeps the frame within transport limits.

This module is deliberately dependency-soft: if Pillow is unavailable or any
step fails, it returns the original bytes unchanged so sending never breaks
just because compression could not run.
"""

from __future__ import annotations

import asyncio
import io

from ...shared import get_logger

logger = get_logger()

# JPEG quality ladder tried in order when an image is over budget.
_QUALITY_LADDER: tuple[int, ...] = (85, 70, 55, 40)
# Long-edge ceilings tried (px) when quality alone cannot reach the budget.
_DIMENSION_LADDER: tuple[int, ...] = (2560, 1920, 1280)


def _try_import_pil():
    try:
        from PIL import Image

        return Image
    except Exception:  # pragma: no cover - environment without Pillow
        return None


def compress_image(data: bytes, *, max_bytes: int) -> bytes:
    """Compress ``data`` toward ``max_bytes``, returning the smallest result.

    Returns the original bytes unchanged when already within budget, when
    Pillow is unavailable, or when any step fails. Never raises for image
    content problems; callers can treat the result as send-ready bytes.
    """
    if max_bytes <= 0 or len(data) <= max_bytes:
        return data

    pil = _try_import_pil()
    if pil is None:
        logger.debug("[compress] Pillow unavailable, sending original bytes")
        return data

    try:
        with pil.open(io.BytesIO(data)) as image:
            image.load()
            rgb = image.convert("RGB")
    except Exception as exc:
        logger.warning("[compress] failed to decode image, keep original: %s", exc)
        return data

    best = data
    orig_w, orig_h = rgb.size

    for max_edge in (None, *_DIMENSION_LADDER):
        candidate = rgb
        if max_edge is not None:
            longest = max(orig_w, orig_h)
            if longest <= max_edge:
                continue
            scale = max_edge / longest
            new_size = (max(1, int(orig_w * scale)), max(1, int(orig_h * scale)))
            try:
                candidate = rgb.resize(new_size, pil.LANCZOS)
            except Exception as exc:
                logger.debug("[compress] resize failed at %dpx: %s", max_edge, exc)
                continue

        for quality in _QUALITY_LADDER:
            try:
                buffer = io.BytesIO()
                candidate.save(buffer, format="JPEG", quality=quality, optimize=True)
            except Exception as exc:
                logger.debug(
                    "[compress] encode failed q=%d edge=%s: %s", quality, max_edge, exc
                )
                continue
            encoded = buffer.getvalue()
            if len(encoded) < len(best):
                best = encoded
            if len(encoded) <= max_bytes:
                logger.debug(
                    "[compress] %d -> %d bytes (q=%d, edge=%s)",
                    len(data),
                    len(encoded),
                    quality,
                    max_edge or "orig",
                )
                return encoded

    logger.debug(
        "[compress] could not reach budget %d, best=%d (orig=%d)",
        max_bytes,
        len(best),
        len(data),
    )
    return best


async def compress_image_async(data: bytes, *, max_bytes: int) -> bytes:
    """Async wrapper running CPU-bound compression off the event loop."""
    return await asyncio.to_thread(compress_image, data, max_bytes=max_bytes)
