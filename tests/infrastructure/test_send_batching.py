"""Tests for send batching logic."""

from __future__ import annotations

from astrbot_plugin_setu.src.infrastructure.sending.send_batching import (
    DIRECT_MAX_IMAGES,
    estimate_base64_bytes,
    split_send_batches,
)


def test_estimate_base64_bytes_empty():
    """Zero raw bytes should return zero base64 bytes."""
    assert estimate_base64_bytes(0) == 0


def test_estimate_base64_bytes_small():
    """Small raw byte sizes should inflate by ~4/3."""
    # 3 raw bytes -> 4 base64 bytes
    assert estimate_base64_bytes(3) == 4
    # 6 raw bytes -> 8 base64 bytes
    assert estimate_base64_bytes(6) == 8


def test_split_send_batches_empty():
    """Empty input should return empty batches."""
    assert split_send_batches([], "image") == []


def test_split_send_batches_single_image():
    """Single image should be one batch."""
    sizes = [1024]
    batches = split_send_batches(sizes, "image")
    assert batches == [[0]]


def test_split_send_batches_respects_image_cap_in_direct_mode():
    """Direct mode should split at 8-image boundary regardless of size."""
    # 10 tiny images, each 100 bytes base64
    sizes = [100] * 10
    batches = split_send_batches(sizes, "image", max_images=DIRECT_MAX_IMAGES)
    assert len(batches) == 2
    assert batches[0] == list(range(8))  # First 8
    assert batches[1] == [8, 9]  # Remaining 2


def test_split_send_batches_forward_mode_ignores_image_cap():
    """Forward mode should ignore image count cap, only respect byte limit."""
    # 10 tiny images, total well under byte limit
    sizes = [100] * 10
    batches = split_send_batches(sizes, "forward", max_images=DIRECT_MAX_IMAGES)
    assert len(batches) == 1
    assert batches[0] == list(range(10))


def test_split_send_batches_respects_byte_limit():
    """Batches should split when cumulative size exceeds byte limit."""
    max_bytes = 1000
    # 3 images: 400, 400, 400 bytes base64
    # First two fit (800), third needs new batch
    sizes = [400, 400, 400]
    batches = split_send_batches(sizes, "image", max_base64_bytes=max_bytes)
    assert len(batches) == 2
    assert batches[0] == [0, 1]
    assert batches[1] == [2]


def test_split_send_batches_oversized_image_gets_own_batch():
    """An image larger than the byte limit should still get its own batch."""
    max_bytes = 1000
    sizes = [500, 2000, 500]  # Middle image is over limit
    batches = split_send_batches(sizes, "image", max_base64_bytes=max_bytes)
    assert len(batches) == 3
    assert batches[0] == [0]
    assert batches[1] == [1]  # Oversized, alone
    assert batches[2] == [2]


def test_split_send_batches_combines_byte_and_count_constraints():
    """Direct mode should respect both byte and image count limits."""
    max_bytes = 5000
    max_images = 8
    # 12 images, each 700 bytes -> first 7 fit under 5000, then count cap kicks in
    sizes = [700] * 12
    batches = split_send_batches(
        sizes, "image", max_images=max_images, max_base64_bytes=max_bytes
    )
    # First batch: min(7 by bytes, 8 by count) = 7
    # Second batch: 5 more (8 total - 7 = 1, but 5 remain, so next 5 fit by bytes? 700*5=3500<5000)
    # Actually: after first 7, we have 5 left. Next batch takes up to 8 and within bytes.
    # 700*5 = 3500 < 5000, so all 5 fit in second batch.
    assert len(batches) == 2
    assert len(batches[0]) == 7
    assert len(batches[1]) == 5
