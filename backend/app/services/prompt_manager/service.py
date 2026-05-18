"""Prompt 管理。

从 app/prompts/ 目录加载 Markdown 模板。支持版本号与变量替换。
缓存：进程内 LRU；改动 prompt 文件需重启或调用 prompt_manager.reload()。
"""
from __future__ import annotations

import string
from functools import lru_cache
from pathlib import Path

PROMPT_ROOT = Path(__file__).resolve().parents[2] / "prompts"
DEFAULT_FALLBACK = (
    "你是 NovelFlow AI 的小说生产工作流节点，"
    "请严格遵守故事圣经、人物状态与世界观规则，输出符合上下文与篇幅要求的内容。"
)


class PromptNotFound(Exception):
    pass


@lru_cache(maxsize=256)
def _read_prompt(category: str, name: str, version: str) -> str:
    candidates = [
        PROMPT_ROOT / category / f"{name}.{version}.md",
        PROMPT_ROOT / category / f"{name}.md",
        PROMPT_ROOT / f"{name}.md",
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8")
    return ""


class PromptManager:
    def load(
        self,
        key: str,
        *,
        version: str = "v1",
        variables: dict[str, str] | None = None,
        strict: bool = False,
    ) -> str:
        """key 形如 'bible/story_bible' 或 'writing/scene_writer'。"""
        if "/" in key:
            category, name = key.split("/", 1)
        else:
            category, name = "", key
        text = _read_prompt(category, name, version)
        if not text:
            if strict:
                raise PromptNotFound(f"prompt_not_found: {key}@{version}")
            text = DEFAULT_FALLBACK
        if variables:
            text = string.Template(text).safe_substitute(variables)
        return text

    def reload(self) -> None:
        _read_prompt.cache_clear()


prompt_manager = PromptManager()
