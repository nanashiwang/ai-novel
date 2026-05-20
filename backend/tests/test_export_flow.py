from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import (
    Chapter,
    DraftVersion,
    ExportFile,
    NovelSpec,
    QuotaBalance,
    Scene,
)
from app.models.common import new_id
from app.workflows import activities


async def _register(client, email: str) -> tuple[str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": email.split("@")[0]},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    return data["access_token"], data["user"]["organization_id"]


async def _seed_project_with_drafts(
    client, db_session, *, email: str, scenes_per_chapter: int = 2, chapters: int = 2
) -> tuple[str, str, dict]:
    """注册 + project + N 章 × M scene + 每 scene 一个 draft（含正文）。

    Free plan 默认有 export_markdown / export_txt entitlement，所以不需要升级。
    """
    token, org_id = await _register(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    now = datetime.now(timezone.utc)
    db_session.add(
        QuotaBalance(
            id=new_id("quota"),
            organization_id=org_id,
            quota_key="monthly_generated_words",
            period_start=now,
            period_end=now + timedelta(days=30),
            limit_value=10000,
            used_value=0,
            reserved_value=0,
            reset_at=now + timedelta(days=30),
        )
    )
    project_res = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"title": "导出测试小说", "genre": "测试体裁", "target_word_count": 5000},
    )
    project_id = project_res.json()["id"]
    db_session.add(
        NovelSpec(
            id=new_id("spec"),
            organization_id=org_id,
            project_id=project_id,
            premise="测试前提",
            theme="测试主题",
        )
    )
    for ci in range(1, chapters + 1):
        chapter_id = new_id("chapter")
        db_session.add(
            Chapter(
                id=chapter_id,
                organization_id=org_id,
                project_id=project_id,
                volume_id=None,
                chapter_index=ci,
                title=f"第{ci}章 测试",
                summary=f"第 {ci} 章摘要",
                goal="测试目标",
                conflict="测试冲突",
                ending_hook="测试钩子",
                status="planned",
            )
        )
        for si in range(1, scenes_per_chapter + 1):
            scene_id = new_id("scene")
            db_session.add(
                Scene(
                    id=scene_id,
                    organization_id=org_id,
                    project_id=project_id,
                    chapter_id=chapter_id,
                    scene_index=si,
                    title=f"场景 {ci}-{si}",
                    time_marker="",
                    location="",
                    characters=[],
                    goal="",
                    conflict="",
                    emotion_start="",
                    emotion_end="",
                    reveal="",
                    hook="",
                    status="drafted",
                )
            )
            db_session.add(
                DraftVersion(
                    id=new_id("draft"),
                    organization_id=org_id,
                    project_id=project_id,
                    chapter_id=chapter_id,
                    scene_id=scene_id,
                    version_type="draft",
                    content=f"这是第 {ci} 章场景 {si} 的正文。",
                    word_count=20,
                    status="draft",
                    parent_version_id=None,
                    created_by="user_x",
                )
            )
    await db_session.commit()
    return org_id, project_id, headers


@pytest.mark.asyncio
async def test_export_markdown_renders_full_project(client, db_engine, db_session, monkeypatch):
    """Markdown 导出包含项目标题、所有章节标题、所有场景正文。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_id, headers = await _seed_project_with_drafts(
        client, db_session, email="export-md@example.com"
    )

    res = await client.post(
        f"/api/v1/projects/{project_id}/exports",
        headers=headers,
        json={"export_type": "markdown"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    export_id = body["id"]
    assert body["export_type"] == "markdown"
    assert body["status"] == "ready"
    assert body["file_size"] > 0
    assert body["file_url"].endswith(f"/exports/{export_id}/download")

    db_session.expire_all()
    exp_row = await db_session.get(ExportFile, export_id)
    assert exp_row is not None
    content = exp_row.content
    assert "# 导出测试小说" in content
    assert "第 1 章" in content and "第 2 章" in content
    assert "场景 1" in content
    assert "这是第 1 章场景 1 的正文。" in content


@pytest.mark.asyncio
async def test_export_txt_renders_full_project(client, db_engine, db_session, monkeypatch):
    """TXT 导出与 Markdown 同结构但用纯文本分隔符。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_id, headers = await _seed_project_with_drafts(
        client, db_session, email="export-txt@example.com"
    )

    res = await client.post(
        f"/api/v1/projects/{project_id}/exports",
        headers=headers,
        json={"export_type": "txt"},
    )
    assert res.status_code == 201, res.text
    export_id = res.json()["id"]

    db_session.expire_all()
    exp_row = await db_session.get(ExportFile, export_id)
    assert exp_row is not None
    content = exp_row.content
    assert content.startswith("导出测试小说")
    assert "===" in content  # 章节分隔
    assert "---" in content  # 场景分隔


@pytest.mark.asyncio
async def test_export_download_returns_file_stream(client, db_engine, db_session, monkeypatch):
    """download endpoint 返回正确 content-type + content-disposition + body。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_id, headers = await _seed_project_with_drafts(
        client, db_session, email="export-dl@example.com"
    )

    create_res = await client.post(
        f"/api/v1/projects/{project_id}/exports",
        headers=headers,
        json={"export_type": "markdown"},
    )
    export_id = create_res.json()["id"]

    dl_res = await client.get(
        f"/api/v1/projects/{project_id}/exports/{export_id}/download",
        headers=headers,
    )
    assert dl_res.status_code == 200, dl_res.text
    assert dl_res.headers["content-type"].startswith("text/markdown")
    assert "attachment" in dl_res.headers["content-disposition"]
    assert "# 导出测试小说" in dl_res.text


@pytest.mark.asyncio
async def test_export_rejects_unsupported_type(client, db_engine, db_session, monkeypatch):
    """暂未支持的格式（docx）返回 404 export_type_not_supported。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_id, headers = await _seed_project_with_drafts(
        client, db_session, email="export-unsupp@example.com"
    )

    res = await client.post(
        f"/api/v1/projects/{project_id}/exports",
        headers=headers,
        json={"export_type": "docx"},
    )
    assert res.status_code == 404, res.text
    assert res.json()["error"]["message"] == "export_type_not_supported"


@pytest.mark.asyncio
async def test_export_rejects_cross_tenant_download(client, db_engine, db_session, monkeypatch):
    """另一个 org 不能下载别人的导出文件。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    _, project_a, headers_a = await _seed_project_with_drafts(
        client, db_session, email="export-org-a@example.com"
    )
    create = await client.post(
        f"/api/v1/projects/{project_a}/exports",
        headers=headers_a,
        json={"export_type": "markdown"},
    )
    export_id = create.json()["id"]

    token_b, _ = await _register(client, "export-org-b@example.com")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    dl = await client.get(
        f"/api/v1/projects/{project_a}/exports/{export_id}/download",
        headers=headers_b,
    )
    assert dl.status_code == 404, dl.text


@pytest.mark.asyncio
async def test_export_empty_project_returns_placeholder(client, db_engine, db_session, monkeypatch):
    """无 chapter 的项目仍能导出，含占位说明。"""
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(activities, "AsyncSessionLocal", Session)

    token, org_id = await _register(client, "export-empty@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    project_res = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"title": "空项目"},
    )
    project_id = project_res.json()["id"]
    await db_session.commit()

    res = await client.post(
        f"/api/v1/projects/{project_id}/exports",
        headers=headers,
        json={"export_type": "markdown"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["file_size"] > 0
    db_session.expire_all()
    exp_row = (
        await db_session.execute(
            select(ExportFile).where(ExportFile.id == body["id"])
        )
    ).scalar_one()
    assert "空项目" in exp_row.content
    assert "尚未生成任何章节" in exp_row.content
