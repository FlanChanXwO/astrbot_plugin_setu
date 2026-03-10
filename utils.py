"""Setu 插件的工具函数。"""

from __future__ import annotations

import base64
import random

from astrbot.core.message.components import Image
from astrbot.api.event import MessageChain
from astrbot.api import logger


def obfuscate_image_bytes(data: bytes) -> bytes:
    """对图片数据进行最小程度的混淆以绕过图片哈希检测。

    在图片数据末尾添加随机字节来改变其哈希值，同时保持图片视觉内容不变。
    这参考了 Java 版 ImageObfuscator 的行为。
    """
    noise = bytes(random.randint(0, 255) for _ in range(8))
    return data + noise


def create_image_chain(images: list[bytes], text: str | None = None) -> MessageChain:
    """创建包含文本和图片的消息链。

    参数:
        images: 图片字节数据列表。
        text: 可选的文本消息。

    返回:
        可发送的消息链。
    """
    chain = MessageChain()
    if text:
        chain.message(text)
    for img_data in images:
        b64 = base64.b64encode(img_data).decode("ascii")
        chain.chain.append(Image.fromBase64(b64))
    return chain


def create_obfuscated_image_chain(
    images: list[bytes], text: str | None = None
) -> MessageChain:
    """创建包含混淆图片的消息链。

    参数:
        images: 图片字节数据列表。
        text: 可选的文本消息。

    返回:
        包含混淆图片的消息链。
    """
    chain = MessageChain()
    if text:
        chain.message(text)
    for img_data in images:
        obf = obfuscate_image_bytes(img_data)
        b64 = base64.b64encode(obf).decode("ascii")
        chain.chain.append(Image.fromBase64(b64))
    return chain
