from __future__ import annotations

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
    estimate_words: int = 20_000
    start_immediately: bool = True
    topic: str = ""
    target_chapters: int | None = None
    scenes_per_chapter: int | None = None
    write_drafts: bool = True


class SceneWriteRequest(APIModel):
    target_words: int = 4_000
    style_hint: str = ""
