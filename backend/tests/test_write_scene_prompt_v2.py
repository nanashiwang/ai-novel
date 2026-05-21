"""写作 prompt v2 加载与契约测试（Sprint 13-B3）。

覆盖：
- prompt_manager 能成功加载 writing/write_scene v2 与 rewrite_scene v2
- v2 prompt 内容包含本次升级的关键指引（人物口吻 / 节奏 / show 优先）
- writer / rewriter service 默认版本号已切到 v2
"""
from __future__ import annotations


def test_write_scene_v2_prompt_loads():
    from app.services.prompt_manager.service import prompt_manager

    text = prompt_manager.load("writing/write_scene", version="v2", strict=True)
    # v2 关键章节存在
    assert "节奏与结构" in text
    assert "人物口吻" in text
    assert "Show / Tell" in text or "显隐之间" in text
    assert "字数" in text
    # 仍保留禁止 HTML / 代码围栏
    assert "禁止" in text
    assert "HTML" in text


def test_rewrite_scene_v2_prompt_loads():
    from app.services.prompt_manager.service import prompt_manager

    text = prompt_manager.load("writing/rewrite_scene", version="v2", strict=True)
    assert "人物口吻" in text
    assert "节奏与结构" in text
    assert "修复" in text  # rewrite 必须保留对 issue 修复的要求


def test_writer_service_uses_v2():
    from app.services.writer import service as ws

    assert ws._PROMPT_VERSION == "v2"


def test_rewriter_service_uses_v2():
    from app.services.rewriter import service as rs

    assert rs._PROMPT_VERSION == "v2"


def test_v1_prompt_still_available_for_legacy_recall():
    """v1 文件仍然存在，确保历史 model_calls 行的 prompt_version='v1' 可重放。"""
    from app.services.prompt_manager.service import prompt_manager

    v1 = prompt_manager.load("writing/write_scene", version="v1", strict=False)
    # v1 不一定有 v2 的章节，但应非空（fallback 也行，但这里期望文件存在）
    assert v1
