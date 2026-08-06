"""随机本子 PDF 的平台发送链构造。"""

from __future__ import annotations

import re

import astrbot.api.message_components as Comp

from ..doujinshi import GeneratedDoujinshiPdf
from .platform_capabilities import supports_forward_messages


def build_doujinshi_file_chain(
    generated: GeneratedDoujinshiPdf,
    *,
    platform_name: str | None,
    self_id: str | int | None,
) -> list[Comp.BaseMessageComponent]:
    """按平台能力构造 PDF 文件消息链。

    OneBot 平台使用一个包含文件段的合并转发节点；若上游实际提供标题或
    原始地址，则按标题、URL 顺序追加纯文本节点。其他平台只返回普通文件段，
    这样不会向不支持 OneBot 节点协议的平台发送不兼容的消息结构。
    """
    file_name = get_doujinshi_file_name(generated)
    file_component = Comp.File(name=file_name, file=str(generated.path))
    if not supports_forward_messages(platform_name):
        return [file_component]

    uin = str(self_id or "")
    nodes = [
        Comp.Node(
            content=[file_component],
            name=generated.gallery.title,
            uin=uin,
        )
    ]
    for label, value in (
        ("标题", generated.gallery.upstream_title),
        ("原始地址", generated.gallery.source_url),
    ):
        if value:
            nodes.append(
                Comp.Node(
                    content=[Comp.Plain(text=value)],
                    name=label,
                    uin=uin,
                )
            )
    return [Comp.Nodes(nodes)]


def get_doujinshi_file_name(generated: GeneratedDoujinshiPdf) -> str:
    """使用本子标题作为文件名，并移除平台不接受的路径字符。"""
    title = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", generated.gallery.title).strip(" .")
    if not title:
        title = f"随机本子-{generated.gallery.id}"
    return f"{title}.pdf"


__all__ = ["build_doujinshi_file_chain", "get_doujinshi_file_name"]
