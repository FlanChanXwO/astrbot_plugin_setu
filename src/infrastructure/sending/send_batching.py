"""Split a sequence of images into send batches that respect platform limits.

Two independent walls constrain a single OneBot message (both measured on the
live dev NapCat, see ``docs/project/sending-limits.md``):

- **Transport (WebSocket frame)**: the whole action JSON — with every image
  inlined as ``base64://`` — travels as one WS frame, capped at ~50 MiB on the
  AstrBot -> NapCat link. We batch against a lower safety line to leave margin.
- **Application (NTQQ)**: a single ``send_group_msg`` aggregates at most 8
  images; the 9th onward times out regardless of byte size. Merge-forward
  (``send_group_forward_msg``) handles each node independently and has no such
  per-message image cap, so only the byte wall applies there.

This module is pure (operates on byte-size estimates) so it is unit-testable
without touching the network or image components.
"""

from __future__ import annotations

# Single OneBot ``send_group_msg`` aggregates at most this many images.
DIRECT_MAX_IMAGES = 8
# Base64 safety line (bytes) for one action frame; below the ~50 MiB hard wall.
DEFAULT_SAFETY_BASE64_BYTES = 40 * 1024 * 1024


def estimate_base64_bytes(raw_bytes: int) -> int:
    """Estimate the base64-encoded size of ``raw_bytes`` raw image bytes."""
    if raw_bytes <= 0:
        return 0
    return (raw_bytes + 2) // 3 * 4


def split_send_batches(
    base64_sizes: list[int],
    mode: str,
    *,
    max_images: int = DIRECT_MAX_IMAGES,
    max_base64_bytes: int = DEFAULT_SAFETY_BASE64_BYTES,
) -> list[list[int]]:
    """Group image indices into batches that fit one OneBot message.

    Args:
        base64_sizes: Per-image estimated base64 byte sizes, in send order.
        mode: Effective send mode (``"forward"`` removes the image-count cap).
        max_images: Per-batch image cap for non-forward modes.
        max_base64_bytes: Per-batch base64 byte budget (both modes).

    Returns:
        A list of batches, each a list of indices into ``base64_sizes``. Every
        image lands in exactly one batch; an image larger than the byte budget
        still gets its own single-image batch rather than being dropped.
    """
    count = len(base64_sizes)
    if count <= 0:
        return []

    image_cap = count if mode == "forward" else max(1, max_images)

    batches: list[list[int]] = []
    current: list[int] = []
    current_bytes = 0

    for index, size in enumerate(base64_sizes):
        over_bytes = current and current_bytes + size > max_base64_bytes
        over_count = len(current) >= image_cap
        if over_bytes or over_count:
            batches.append(current)
            current = []
            current_bytes = 0
        current.append(index)
        current_bytes += size

    if current:
        batches.append(current)
    return batches
