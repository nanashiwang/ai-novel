from .common import APIModel


class ProjectCreate(APIModel):
    title: str
    premise: str = ""
    genre: str = ""
    target_word_count: int = 300_000
    target_chapter_count: int = 48
    style: str = ""


class ProjectResponse(APIModel):
    id: str
    organization_id: str
    title: str
    genre: str
    target_word_count: int
    target_chapter_count: int
    status: str


class GenerateNovelRequest(APIModel):
    mode: str = "full_novel"
    estimate_words: int = 20_000
    start_immediately: bool = True


class SceneWriteRequest(APIModel):
    target_words: int = 4_000
    style_hint: str = ""
