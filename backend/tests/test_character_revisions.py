"""人物字段版本链端到端测试。

覆盖：
- 创建 character 后修改：每个变化字段产 source='user_edit' status='applied' revision
- 应用 / 驳回 / 回滚 pending revision
- 同字段多次修改：旧 applied 标 superseded
- pending 计数聚合
"""
from __future__ import annotations

import pytest


async def _register_with_project(client, email: str) -> tuple[str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": email.split("@")[0]},
    )
    assert res.status_code == 201, res.text
    token = res.json()["access_token"]
    project_res = await client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "动态人物测试", "genre": "悬疑"},
    )
    assert project_res.status_code in (200, 201), project_res.text
    return token, project_res.json()["id"]


async def _create_character(client, token, project_id, **overrides) -> dict:
    payload = {
        "name": "林秋",
        "role": "protagonist",
        "description": "失忆的档案管理员",
        "personality": "内敛",
        "motivation": "找回记忆",
        "secret": "",
        "arc": "",
        "relationships": {},
        "current_state": {},
    }
    payload.update(overrides)
    res = await client.post(
        f"/api/v1/projects/{project_id}/characters",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 201, res.text
    return res.json()


@pytest.mark.asyncio
async def test_character_update_produces_applied_revisions(client):
    """编辑 character 字段 → 每个变化字段生成 source='user_edit' status='applied' 记录。"""
    token, project_id = await _register_with_project(client, "char-rev-1@example.com")
    character = await _create_character(client, token, project_id)
    headers = {"Authorization": f"Bearer {token}"}

    # 修改 motivation 和 personality
    patch = await client.patch(
        f"/api/v1/projects/{project_id}/characters/{character['id']}",
        headers=headers,
        json={
            **character,
            "motivation": "找回记忆并查清姐姐死因",
            "personality": "内敛且执着",
        },
    )
    assert patch.status_code == 200

    # 列出 revisions
    rev_res = await client.get(
        f"/api/v1/projects/{project_id}/characters/{character['id']}/revisions",
        headers=headers,
    )
    assert rev_res.status_code == 200
    revisions = rev_res.json()
    # 两个字段变化 → 两条 revision，都是 user_edit + applied
    assert len(revisions) == 2
    assert all(r["source"] == "user_edit" for r in revisions)
    assert all(r["status"] == "applied" for r in revisions)
    fields = {r["field"] for r in revisions}
    assert fields == {"motivation", "personality"}


@pytest.mark.asyncio
async def test_character_update_same_field_supersedes_old(client):
    """同字段二次修改：旧 applied 应标 superseded，新 applied 生效。"""
    token, project_id = await _register_with_project(client, "char-rev-2@example.com")
    character = await _create_character(client, token, project_id)
    headers = {"Authorization": f"Bearer {token}"}

    for new_motivation in ("v1", "v2"):
        await client.patch(
            f"/api/v1/projects/{project_id}/characters/{character['id']}",
            headers=headers,
            json={**character, "motivation": new_motivation},
        )

    revs = (await client.get(
        f"/api/v1/projects/{project_id}/characters/{character['id']}/revisions",
        headers=headers,
    )).json()
    motivation_revs = [r for r in revs if r["field"] == "motivation"]
    # 应有 2 条；其中 1 条 applied（最新 v2），1 条 superseded（旧 v1）
    assert len(motivation_revs) == 2
    statuses = sorted(r["status"] for r in motivation_revs)
    assert statuses == ["applied", "superseded"]
    applied = next(r for r in motivation_revs if r["status"] == "applied")
    assert applied["new_value"] == "v2"


@pytest.mark.asyncio
async def test_character_revision_rollback(client):
    """把历史 revision 重新 apply：character 字段回到目标值，新增一条 user_edit applied 记录。"""
    token, project_id = await _register_with_project(client, "char-rev-3@example.com")
    character = await _create_character(client, token, project_id)
    headers = {"Authorization": f"Bearer {token}"}

    # 两次修改：v1 → v2
    await client.patch(
        f"/api/v1/projects/{project_id}/characters/{character['id']}",
        headers=headers,
        json={**character, "motivation": "v1"},
    )
    await client.patch(
        f"/api/v1/projects/{project_id}/characters/{character['id']}",
        headers=headers,
        json={**character, "motivation": "v2"},
    )

    # 找到第一条（v1）revision
    revs = (await client.get(
        f"/api/v1/projects/{project_id}/characters/{character['id']}/revisions",
        headers=headers,
    )).json()
    v1_rev = next(r for r in revs if r["new_value"] == "v1")

    # 回滚到 v1
    rollback = await client.post(
        (
            f"/api/v1/projects/{project_id}/characters/{character['id']}"
            f"/revisions/{v1_rev['id']}/rollback"
        ),
        headers=headers,
    )
    assert rollback.status_code == 200, rollback.text
    rollback_rev = rollback.json()
    assert rollback_rev["new_value"] == "v1"
    assert rollback_rev["status"] == "applied"
    assert "回滚" in rollback_rev["reason"]

    # character 当前值应为 v1
    char_res = await client.get(
        f"/api/v1/projects/{project_id}/characters",
        headers=headers,
    )
    current = next(c for c in char_res.json() if c["id"] == character["id"])
    assert current["motivation"] == "v1"


@pytest.mark.asyncio
async def test_character_revisions_pending_count(client, db_session):
    """pending-count 聚合：直接造一条 pending revision，确认 count 为 1。"""
    from app.models.character_revision import CharacterRevision
    from app.models.common import new_id

    token, project_id = await _register_with_project(client, "char-rev-4@example.com")
    character = await _create_character(client, token, project_id)
    headers = {"Authorization": f"Bearer {token}"}

    # 直接造 pending 记录（模拟 AI 推演产出，Phase B 才有真实链路）
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    db_session.add(
        CharacterRevision(
            id=new_id("char_rev"),
            organization_id=me["organization_id"],
            project_id=project_id,
            character_id=character["id"],
            field="current_state",
            old_value={},
            new_value={"abilities": ["识别加密签名"]},
            reason="第 10 章主角破解了一份七年前的加密文件",
            source="ai_inferred",
            scene_id=None,
            status="pending",
            created_by=me["id"],
        )
    )
    await db_session.commit()

    count_res = await client.get(
        f"/api/v1/projects/{project_id}/character-revisions/pending-count",
        headers=headers,
    )
    assert count_res.status_code == 200
    counts = count_res.json()
    assert {"character_id": character["id"], "pending_count": 1} in counts


@pytest.mark.asyncio
async def test_extract_state_changes_persists_pending_revisions(
    client, db_session, monkeypatch
):
    """Phase B：mock model_gateway.generate_json，验证 LLM 输出被正确落
    到 character_revisions（status='pending'）。"""
    from app.services.character_tracker import extract as extract_module
    from app.services.model_gateway import service as gateway_module

    token, project_id = await _register_with_project(client, "extract-1@example.com")
    character = await _create_character(client, token, project_id)
    headers = {"Authorization": f"Bearer {token}"}

    # mock model_gateway.generate_json 直接返回结构化结果
    async def fake_generate_json(self, session, **kwargs):  # noqa: ANN001
        return {
            "changes": [
                {
                    "character_name": character["name"],
                    "field": "current_state",
                    "new_value": {"abilities": ["识别加密签名"]},
                    "evidence": "他对加密签名产生了直觉——「这是父亲的笔迹。」",
                },
                {
                    "character_name": character["name"],
                    "field": "motivation",
                    "new_value": "找回记忆并查清姐姐死因",
                    "evidence": "新动机出现",
                },
            ]
        }

    monkeypatch.setattr(
        gateway_module.ModelGateway, "generate_json", fake_generate_json
    )

    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    written = await extract_module.extract_state_changes_from_scene(
        db_session,
        organization_id=me["organization_id"],
        project_id=project_id,
        scene_id="scene_test_id",
        scene_content="林秋第一次发现签名是父亲的笔迹。",
        created_by=me["id"],
    )
    await db_session.commit()

    assert written == 2

    # 应有 2 条 pending revisions
    rev_res = await client.get(
        f"/api/v1/projects/{project_id}/characters/{character['id']}/revisions",
        headers=headers,
        params={"status": "pending"},
    )
    revisions = rev_res.json()
    assert len(revisions) == 2
    assert all(r["status"] == "pending" for r in revisions)
    assert all(r["source"] == "ai_inferred" for r in revisions)
    fields = {r["field"] for r in revisions}
    assert fields == {"current_state", "motivation"}


@pytest.mark.asyncio
async def test_extract_skips_unknown_characters_and_invalid_fields(
    client, db_session, monkeypatch
):
    """LLM 输出陌生人物或字段时静默跳过，不报错。"""
    from app.services.character_tracker import extract as extract_module
    from app.services.model_gateway import service as gateway_module

    token, project_id = await _register_with_project(client, "extract-2@example.com")
    character = await _create_character(client, token, project_id)
    headers = {"Authorization": f"Bearer {token}"}

    async def fake_generate_json(self, session, **kwargs):  # noqa: ANN001
        return {
            "changes": [
                # 陌生人物（不在 character 卡）
                {
                    "character_name": "未知人物",
                    "field": "motivation",
                    "new_value": "abc",
                    "evidence": "x",
                },
                # 不在白名单的 field
                {
                    "character_name": character["name"],
                    "field": "level",
                    "new_value": 10,
                    "evidence": "x",
                },
                # 合法变化
                {
                    "character_name": character["name"],
                    "field": "personality",
                    "new_value": "执着",
                    "evidence": "对真相有偏执",
                },
            ]
        }

    monkeypatch.setattr(
        gateway_module.ModelGateway, "generate_json", fake_generate_json
    )
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    written = await extract_module.extract_state_changes_from_scene(
        db_session,
        organization_id=me["organization_id"],
        project_id=project_id,
        scene_id="scene_test_id",
        scene_content="...",
        created_by=me["id"],
    )
    await db_session.commit()
    # 只有 1 条合法 → 1 条落库
    assert written == 1


@pytest.mark.asyncio
async def test_character_timeline_groups_by_chapter(client, db_session):
    """Phase C：apply 一条带 scene_id 的 revision，timeline 应该把它聚到对应章节下；
    手动编辑（无 scene_id）落到"未关联章节"桶。"""
    from app.models.chapter import Chapter
    from app.models.character_revision import CharacterRevision
    from app.models.common import new_id
    from app.models.scene import Scene

    token, project_id = await _register_with_project(client, "timeline-1@example.com")
    character = await _create_character(client, token, project_id)
    headers = {"Authorization": f"Bearer {token}"}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()

    # 造一条 Chapter + Scene
    chapter = Chapter(
        id=new_id("chapter"),
        organization_id=me["organization_id"],
        project_id=project_id,
        volume_id=None,
        chapter_index=5,
        title="第五章 转折",
        summary="",
        goal="",
        conflict="",
        ending_hook="",
        status="planned",
    )
    scene = Scene(
        id=new_id("scene"),
        organization_id=me["organization_id"],
        project_id=project_id,
        chapter_id=chapter.id,
        scene_index=1,
        title="",
        time_marker="",
        location="",
        characters=[],
        goal="",
        conflict="",
        emotion_start="",
        emotion_end="",
        reveal="",
        hook="",
        status="planned",
    )
    db_session.add_all([chapter, scene])
    await db_session.flush()

    # 1) AI 推演产出 pending revision（带 scene_id）
    pending_rev = CharacterRevision(
        id=new_id("char_rev"),
        organization_id=me["organization_id"],
        project_id=project_id,
        character_id=character["id"],
        field="current_state",
        old_value={},
        new_value={"abilities": ["识别加密签名"]},
        reason="第 5 章主角破解了加密文件",
        source="ai_inferred",
        scene_id=scene.id,
        status="pending",
        created_by=me["id"],
    )
    db_session.add(pending_rev)
    await db_session.commit()

    # 2) 用户应用
    apply_res = await client.post(
        f"/api/v1/projects/{project_id}/characters/{character['id']}/revisions/{pending_rev.id}/apply",
        headers=headers,
    )
    assert apply_res.status_code == 200

    # 3) 用户手动编辑 personality（无 scene_id）
    # 先 GET 最新 character（current_state 已被 AI 推演应用更新），避免用 stale 值
    latest_chars = (await client.get(
        f"/api/v1/projects/{project_id}/characters",
        headers=headers,
    )).json()
    fresh = next(c for c in latest_chars if c["id"] == character["id"])
    await client.patch(
        f"/api/v1/projects/{project_id}/characters/{character['id']}",
        headers=headers,
        json={**fresh, "personality": "内敛且执着"},
    )

    # 4) 拉 timeline
    timeline_res = await client.get(
        f"/api/v1/projects/{project_id}/characters/{character['id']}/revisions/timeline",
        headers=headers,
    )
    assert timeline_res.status_code == 200, timeline_res.text
    timeline = timeline_res.json()

    # 应有 2 桶：第 5 章 + 未关联章节
    assert len(timeline) == 2
    # 第一个 entry 应是第 5 章
    chapter_entry = timeline[0]
    assert chapter_entry["chapter_index"] == 5
    assert chapter_entry["chapter_title"] == "第五章 转折"
    assert len(chapter_entry["revisions"]) == 1
    assert chapter_entry["revisions"][0]["field"] == "current_state"
    # 第二个 entry 是未关联章节，包含 personality 变化
    unanchored = timeline[1]
    assert unanchored["chapter_index"] is None
    assert any(r["field"] == "personality" for r in unanchored["revisions"])


@pytest.mark.asyncio
async def test_context_builder_character_actions_segment(client, db_session):
    """Phase D：build_for_scene_writing 注入 character_actions 段，
    召回 focus_names 中角色最近出场场景的 draft 摘要。"""
    from app.models.chapter import Chapter
    from app.models.common import new_id
    from app.models.draft_version import DraftVersion
    from app.models.project import NovelSpec, Project
    from app.models.scene import Scene
    from app.services.context_builder import ContextBuilder

    token, project_id = await _register_with_project(client, "ctx-actions@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    org_id = me["organization_id"]

    project = (
        await db_session.execute(
            __import__("sqlalchemy").select(Project).where(Project.id == project_id)
        )
    ).scalar_one()

    spec = NovelSpec(
        id=new_id("spec"),
        organization_id=org_id,
        project_id=project_id,
        premise="测试前提",
        theme="测试主题",
        genre="奇幻",
        tone="紧张",
        target_reader="—",
        narrative_pov="第三人称",
        style_guide="—",
        constraints=[],
        continuity_rules=[],
    )
    db_session.add(spec)

    # 造 2 章，每章 1 场，主角"林秋"都出场，drafts 有内容
    chapter1 = Chapter(
        id=new_id("chapter"), organization_id=org_id, project_id=project_id,
        volume_id=None, chapter_index=1, title="开端", summary="", goal="", conflict="",
        ending_hook="", status="drafted",
    )
    chapter2 = Chapter(
        id=new_id("chapter"), organization_id=org_id, project_id=project_id,
        volume_id=None, chapter_index=2, title="转折", summary="", goal="", conflict="",
        ending_hook="", status="drafted",
    )
    scene1 = Scene(
        id=new_id("scene"), organization_id=org_id, project_id=project_id,
        chapter_id=chapter1.id, scene_index=1, title="夜雨", time_marker="",
        location="", characters=["林秋"], goal="", conflict="",
        emotion_start="", emotion_end="", reveal="", hook="", status="drafted",
    )
    scene2 = Scene(
        id=new_id("scene"), organization_id=org_id, project_id=project_id,
        chapter_id=chapter2.id, scene_index=1, title="清晨", time_marker="",
        location="", characters=["林秋"], goal="", conflict="",
        emotion_start="", emotion_end="", reveal="", hook="", status="planned",
    )
    draft1 = DraftVersion(
        id=new_id("draft"), organization_id=org_id, project_id=project_id,
        chapter_id=chapter1.id, scene_id=scene1.id, version_type="draft",
        content="林秋走进档案馆，第一次触摸那份七年前的封禁文件。",
        content_format="markdown", word_count=20, status="draft",
        parent_version_id=None, created_by=me["id"],
    )
    db_session.add_all([chapter1, chapter2, scene1, scene2, draft1])
    await db_session.commit()

    # scene2 是"当前待写"的 scene，focus_names = ["林秋"]
    builder = ContextBuilder(total_budget=4000)
    ctx = await builder.build_for_scene_writing(
        db_session, project=project, spec=spec, chapter=chapter2, scene=scene2
    )
    labels = [s.label for s in ctx.segments]
    assert "character_actions" in labels
    actions_seg = next(s for s in ctx.segments if s.label == "character_actions")
    assert actions_seg.trusted is True
    # 应包含林秋的标题与第 1 章场景 1 的摘要
    assert "【林秋】" in actions_seg.content
    assert "第 1 章场景 1" in actions_seg.content
    assert "档案馆" in actions_seg.content


@pytest.mark.asyncio
async def test_context_builder_character_actions_empty_when_no_focus(client, db_session):
    """没有 focus_names（场景未指定 characters）时 character_actions 段为空。"""
    from app.models.chapter import Chapter
    from app.models.common import new_id
    from app.models.project import NovelSpec, Project
    from app.models.scene import Scene
    from app.services.context_builder import ContextBuilder

    token, project_id = await _register_with_project(client, "ctx-empty@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    org_id = me["organization_id"]

    project = (
        await db_session.execute(
            __import__("sqlalchemy").select(Project).where(Project.id == project_id)
        )
    ).scalar_one()
    spec = NovelSpec(
        id=new_id("spec"), organization_id=org_id, project_id=project_id,
        premise="", theme="", genre="", tone="", target_reader="",
        narrative_pov="", style_guide="", constraints=[], continuity_rules=[],
    )
    chapter = Chapter(
        id=new_id("chapter"), organization_id=org_id, project_id=project_id,
        volume_id=None, chapter_index=1, title="—", summary="", goal="",
        conflict="", ending_hook="", status="planned",
    )
    scene = Scene(
        id=new_id("scene"), organization_id=org_id, project_id=project_id,
        chapter_id=chapter.id, scene_index=1, title="—", time_marker="",
        location="", characters=[], goal="", conflict="",
        emotion_start="", emotion_end="", reveal="", hook="", status="planned",
    )
    db_session.add_all([spec, chapter, scene])
    await db_session.commit()

    builder = ContextBuilder(total_budget=4000)
    ctx = await builder.build_for_scene_writing(
        db_session, project=project, spec=spec, chapter=chapter, scene=scene
    )
    actions_seg = next(s for s in ctx.segments if s.label == "character_actions")
    assert actions_seg.content == ""
