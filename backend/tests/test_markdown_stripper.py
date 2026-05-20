"""markdown_stripper：把 markdown 字符串剥离为纯文本。

覆盖 StarterKit 输出的语法子集；不依赖外部库。
"""
from __future__ import annotations

from app.services.exporter.markdown_stripper import strip_markdown


def test_strip_headings() -> None:
    md = "# 一级\n\n## 二级\n\n### 三级\n\n正文"
    assert strip_markdown(md) == "一级\n\n二级\n\n三级\n\n正文"


def test_strip_inline_marks() -> None:
    md = "他**走进来**，对她*微笑*，然后~~退出~~了。"
    assert strip_markdown(md) == "他走进来，对她微笑，然后退出了。"


def test_strip_alt_emphasis() -> None:
    md = "这里 __也是粗体__ 和 _也是斜体_ 的写法。"
    assert strip_markdown(md) == "这里 也是粗体 和 也是斜体 的写法。"


def test_strip_inline_code() -> None:
    md = "看下 `editor.commands.setContent()` 这个 API。"
    assert strip_markdown(md) == "看下 editor.commands.setContent() 这个 API。"


def test_strip_blockquote() -> None:
    md = "> 那是最好的时代\n> 那是最坏的时代"
    assert strip_markdown(md) == "那是最好的时代\n那是最坏的时代"


def test_strip_lists() -> None:
    md = "- 苹果\n- 橙子\n  - 蜜橘\n\n1. 第一\n2. 第二"
    out = strip_markdown(md)
    assert "• 苹果" in out
    assert "• 橙子" in out
    assert "蜜橘" in out
    assert "第一" in out and "第二" in out


def test_strip_horizontal_rule() -> None:
    md = "上半段\n\n---\n\n下半段"
    assert "---" not in strip_markdown(md)
    assert "上半段" in strip_markdown(md)
    assert "下半段" in strip_markdown(md)


def test_strip_fenced_code_block() -> None:
    md = "```python\nprint('hi')\n```"
    assert strip_markdown(md) == "print('hi')"


def test_strip_links_and_images() -> None:
    md = "看一下 [文档](https://example.com) 和 ![截图](https://example.com/a.png)。"
    assert strip_markdown(md) == "看一下 文档 和 截图。"


def test_strip_hard_break_trailing_spaces() -> None:
    md = "第一行  \n第二行"
    assert strip_markdown(md) == "第一行\n第二行"


def test_strip_empty_input() -> None:
    assert strip_markdown("") == ""
    assert strip_markdown(None) == ""  # type: ignore[arg-type]


def test_strip_collapses_excess_blank_lines() -> None:
    md = "段一\n\n\n\n段二"
    assert strip_markdown(md) == "段一\n\n段二"


def test_strip_preserves_plain_text() -> None:
    # 旧 'text' 数据通过 stripper 不会被破坏（无标记可剥）
    text = "纯文本场景正文，无任何 markdown 语法。\n\n第二段开始。"
    assert strip_markdown(text) == text


def test_strip_mixed_complex_paragraph() -> None:
    md = (
        "## 第三场\n\n"
        "**林秋**走进*昏暗*的房间，他想起 [那封信](url)。\n\n"
        "> 「你不该来。」\n\n"
        "- 灯熄了\n- 风停了"
    )
    out = strip_markdown(md)
    assert out.startswith("第三场")
    assert "林秋走进昏暗的房间" in out
    assert "那封信" in out
    assert "「你不该来。」" in out
    assert "• 灯熄了" in out and "• 风停了" in out
    assert "*" not in out and "#" not in out and ">" not in out
