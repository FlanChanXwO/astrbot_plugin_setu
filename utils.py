"""Setu 插件的工具函数。"""

from __future__ import annotations

import base64
import random

from astrbot.api.event import MessageChain
from astrbot.core.message.components import Image


def obfuscate_image_bytes(data: bytes) -> bytes:
    """对图片数据进行最小程度的混淆以绕过图片哈希检测。

    在图片数据末尾添加随机字节来改变其哈希值，同时保持图片视觉内容不变。
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


def cn_to_an(cn_num: str) -> int:
    """中文数字转阿拉伯数字

    参数:
        cn_num: 中文数字。

    返回:
        阿拉伯数字。
    """

    # 定义对应关系
    num_dict = {
        "零": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    unit_dict = {"十": 10, "百": 100, "千": 1000, "万": 10000, "亿": 100000000}

    res = 0
    unit = 1  # 当前单位
    temp = 0  # 累加临时值

    # 倒序处理
    for i in range(len(cn_num) - 1, -1, -1):
        char = cn_num[i]
        if char in unit_dict:
            val = unit_dict[char]
            if val >= 10000:  # 处理万、亿大单位
                if val > unit:
                    unit = val
                    temp = 0  # 重置临时值
                else:
                    unit *= val
            else:
                if val >= temp:
                    temp = val
                else:
                    temp *= val
        elif char in num_dict:
            res += num_dict[char] * (temp if temp > 0 else 1) * unit
            temp = 0

    # 特殊处理开头是“十”的情况，如“十四”
    if cn_num.startswith("十"):
        res += 10
    return res
