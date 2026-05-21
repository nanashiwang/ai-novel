from __future__ import annotations

from pydantic import Field

from .common import APIModel


class ProjectCreate(APIModel):
    title: str
    premise: str = ""
    genre: str = ""
    target_word_count: int = 300_000
    target_chapter_count: int = 48
    style: str = ""
    target_reader: str = ""
    cover_url: str = ""
    tags: list[str] = []


class ProjectResponse(APIModel):
    id: str
    organization_id: str
    title: str
    genre: str
    target_word_count: int
    target_chapter_count: int
    current_word_count: int = 0
    completed_chapter_count: int = 0
    language: str
    style: str
    status: str
    cover_url: str = ""
    tags: list[str] = []
    target_reader: str = ""


class GenerateNovelRequest(APIModel):
    mode: str = "full_novel"
    # estimate_words 决定父 full_novel job 的 reserved_quota；上限按
    # 1,500,000 字（约 50 章 × 3 万字）保守拉一些，避免 Free 误调爆配额。
    # Pro+ 套餐若实际需求更大，可以分多个 full_novel job 串起来跑。
    estimate_words: int = Field(default=20_000, ge=1_000, le=1_500_000)
    start_immediately: bool = True
    topic: str = ""
    # None → activity 内回落到 project.target_chapter_count；上限与
    # MAX_OUTLINE_CHAPTERS 对齐（contracts.py = 2000）。
    target_chapters: int | None = Field(default=None, ge=1, le=2000)
    scenes_per_chapter: int = Field(default=3, ge=1, le=8)
    write_drafts: bool = True


class SceneWriteRequest(APIModel):
    target_words: int = 4_000
    style_hint: str = ""
