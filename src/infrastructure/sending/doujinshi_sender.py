"""随机本子文件的发送链构造。"""

from __future__ import annotations

import re

import astrbot.api.message_components as Comp

from ..doujinshi import GeneratedDoujinshiFile


def build_doujinshi_file_chain(
    generated: GeneratedDoujinshiFile,
    *,
    platform_name: str | None = None,
    self_id: str | int | None = None,
) -> list[Comp.BaseMessageComponent]:
    """构造跨平台通用的普通文件消息链。

    本子不再包装为 ``Nodes`` 合并转发；PDF 和 ZIP 都通过单个 ``File``
    消息发送，由调用方决定是否需要走 OneBot 原始直发以取得撤回所需的
    ``message_id``。保留旧的 ``platform_name`` / ``self_id`` 关键字参数仅为
    兼容外部调用方，它们不会改变普通文件发送行为。
    """
    file_name = get_doujinshi_file_name(generated)
    return [Comp.File(name=file_name, file=str(generated.path))]


def get_doujinshi_file_name(generated: GeneratedDoujinshiFile) -> str:
    """使用本子标题作为文件名，并移除平台不接受的路径字符。"""
    title = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", generated.gallery.title).strip(" .")
    if not title:
        title = f"随机本子-{generated.gallery.id}"
    mode = getattr(generated, "mode", "pdf")
    mode_value = getattr(mode, "value", mode)
    if mode_value == "pdf":
        suffix = ".pdf"
    elif mode_value == "archive":
        suffix = ".zip"
    else:
        raise ValueError(f"不支持的随机本子文件模式: {mode_value!r}")
    return f"{title}{suffix}"


__all__ = ["build_doujinshi_file_chain", "get_doujinshi_file_name"]
