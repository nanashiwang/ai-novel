"""章后润色 pass 服务（Sprint 17-C 方案 3）。

每章所有 scene 都 drafted 后整章润色为一份 chapter-level draft，
落到 draft_versions(version_type='polish'). 用户审阅后选择是否替代
scene-level 版本。
"""
from app.services.polisher.service import polish_chapter

__all__ = ["polish_chapter"]
