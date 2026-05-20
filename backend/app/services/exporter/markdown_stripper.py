"""Markdown -> 纯文本剥离器。

用于 TXT 导出：把 markdown 字符串去除标记语法，返回 plain text。
不引入新依赖（markdown-it-py / mistune）—— 正则覆盖 StarterKit 输出的
markdown 子集即可（heading / bold / italic / strike / code / list / quote /
hr / hardBreak），其余罕见语法不动也不会破坏阅读。

策略：
- 行内：去除 **/*/_/__/~~/` 标记，保留文本内容
- 行级：去除 #/>/-/* 前缀，列表项加圆点 "• "
- 块：水平线、围栏代码块去除标记
- 末尾换行规整
"""
from __future__ import annotations

import re

# 按"行级 → 行内 → 围栏代码块"分三遍处理，避免规则相互污染
_FENCED_CODE_RE = re.compile(r"```[a-zA-Z0-9_-]*\n([\s\S]*?)\n```", re.MULTILINE)
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_BLOCKQUOTE_RE = re.compile(r"^\s{0,3}>\s?", re.MULTILINE)
_BULLET_RE = re.compile(r"^(\s*)([-*+])\s+", re.MULTILINE)
_ORDERED_RE = re.compile(r"^(\s*)\d+\.\s+", re.MULTILINE)
_HORIZONTAL_RULE_RE = re.compile(r"^\s{0,3}([-*_])\s*\1\s*\1[-*_\s]*$", re.MULTILINE)

_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_ITALIC_RE = re.compile(r"(?<![*_])\*([^*\n]+)\*(?!\*)|(?<![*_])_([^_\n]+)_(?!_)")
_STRIKE_RE = re.compile(r"~~([^~]+)~~")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
# Markdown 硬换行：行尾两个空格
_HARD_BREAK_RE = re.compile(r"  +$", re.MULTILINE)


def strip_markdown(md: str) -> str:
    """把 markdown 字符串转为 plain text，保留正文与段落结构。

    用于导出 TXT 与列表预览（前端 toPlainText 是同义工具，但前端额外经过
    marked + DOM strip，差异处对最终用户不可感知）。
    """
    if not md:
        return ""

    text = md

    # 围栏代码块：保留 inner 文本，去掉 ``` 围栏
    text = _FENCED_CODE_RE.sub(lambda m: m.group(1), text)

    # 图片：保留 alt 文本
    text = _IMAGE_RE.sub(r"\1", text)
    # 链接：保留显示文本
    text = _LINK_RE.sub(r"\1", text)

    # 行级
    text = _HORIZONTAL_RULE_RE.sub("", text)
    text = _HEADING_RE.sub("", text)
    text = _BLOCKQUOTE_RE.sub("", text)
    text = _BULLET_RE.sub(r"\1• ", text)
    text = _ORDERED_RE.sub(r"\1", text)

    # 硬换行
    text = _HARD_BREAK_RE.sub("", text)

    # 行内
    # 顺序：bold → italic → strike → code（先去掉 ** 再处理单 *，避免冲突）
    text = _BOLD_RE.sub(lambda m: m.group(1) or m.group(2), text)
    text = _ITALIC_RE.sub(lambda m: m.group(1) or m.group(2), text)
    text = _STRIKE_RE.sub(r"\1", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)

    # 折叠 3+ 连续换行为段落分隔
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
