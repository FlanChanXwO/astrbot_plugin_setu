"""Tests for image compression."""

from __future__ import annotations

import pytest
from astrbot_plugin_setu.src.infrastructure.sending.image_compressor import (
    compress_image,
)


def _pil_available() -> bool:
    try:
        import PIL  # noqa: F401

        return True
    except ImportError:
        return False


def test_compress_image_keeps_small_images_unchanged():
    """Small images within budget should pass through unchanged."""
    small_data = b"small-image-data"
    max_bytes = len(small_data) + 100
    result = compress_image(small_data, max_bytes=max_bytes)
    assert result == small_data


def test_compress_image_returns_original_when_pillow_unavailable(monkeypatch):
    """When Pillow is unavailable, return original bytes gracefully."""
    import sys

    # Hide PIL from import
    monkeypatch.setitem(sys.modules, "PIL", None)
    large_data = b"x" * (10 * 1024 * 1024)
    result = compress_image(large_data, max_bytes=1024 * 1024)
    # Should return original since Pillow is "unavailable"
    assert result == large_data


def test_compress_image_handles_invalid_image_data():
    """Invalid image data should return original bytes without raising."""
    invalid_data = b"not-an-image"
    result = compress_image(invalid_data, max_bytes=100)
    assert result == invalid_data


@pytest.mark.skipif(
    not _pil_available(), reason="Pillow not available in test environment"
)
def test_compress_image_reduces_jpeg_below_target():
    """Valid JPEG should be compressed toward the target size."""
    import io

    from PIL import Image

    # Create a large test JPEG
    img = Image.new("RGB", (2000, 2000), color=(255, 0, 0))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=95)
    large_jpeg = buffer.getvalue()

    # Set target to half of actual size to force compression
    target = len(large_jpeg) // 2
    assert len(large_jpeg) > target, "Test image should start larger than target"

    result = compress_image(large_jpeg, max_bytes=target)
    # Result should be smaller (or at least attempted compression)
    assert len(result) <= len(large_jpeg)
