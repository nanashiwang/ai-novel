"""审稿服务。

输入：当前 scene + 最新 draft 内容。
输出：AuditResultContract（list of AuditIssueItem）。

设计：复用 ContextBuilder.build_for_scene_writing 拿到 bible/chapter/scene
等结构化上下文，加上"请审稿"指令；模型只负责找问题，不重写正文。
"""
from __future__ import annotations

import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.project import NovelSpec, Project
from app.models.scene import Scene
from app.repositories import CharacterRepository, InformationLedgerRepository
from app.schemas.story_generation import AuditResultContract
from app.services.context_builder.service import context_builder
from app.services.model_gateway.service import model_gateway
from app.services.prompt_manager.service import prompt_manager
from app.services.scene_budget import build_scene_budget_plan
from app.services.story_state.prompting import build_anti_forgetting_prompt_block

_PROMPT_AUDIT_SCENE = "audit/audit_scene"
_PROMPT_VERSION = "v1"


class AuditorService:
    async def audit_scene_draft(
        self,
        session: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        job_id: str,
        project: Project,
        spec: NovelSpec,
        chapter: Chapter,
        scene: Scene,
        draft_content: str,
        mode: str = "normal",
    ) -> AuditResultContract:
        """审稿。mode='normal' 为默认 5 维校验；mode='long_range' 时额外
        从 InformationLedger 抽 5 条历史已公开事实注入 prompt，让模型
        重点校验本章是否与历史已公开事实矛盾（Sprint 17-A 防漂移）。"""
        prompt = prompt_manager.load(_PROMPT_AUDIT_SCENE, version=_PROMPT_VERSION)
        ctx = await context_builder.build_for_scene_writing(
            session,
            project=project,
            spec=spec,
            chapter=chapter,
            scene=scene,
        )
        scene_target_words = await _resolve_audit_scene_target_words(
            session,
            organization_id=organization_id,
            chapter=chapter,
            scene=scene,
        )
        anti_forgetting_block, anti_forgetting_meta = await build_anti_forgetting_prompt_block(
            session,
            organization_id=organization_id,
            project_id=project_id,
            chapter=chapter,
            scene=scene,
            purpose="audit",
        )
        draft_word_count = len(draft_content or "")

        long_range_block = ""
        if mode == "long_range":
            try:
                ledger_rows = list(
                    await InformationLedgerRepository(session).list(
                        organization_id=organization_id,
                        project_id=project_id,
                        limit=50,
                    )
                )
                public_facts = [
                    r for r in ledger_rows if r.status in {"partial", "public"} and r.fact
                ]
                if public_facts:
                    sample = random.sample(public_facts, k=min(5, len(public_facts)))
                    bullets = "\n".join(
                        f"- [{r.status}, importance={r.importance}] {r.fact}"
                        for r in sample
                    )
                    long_range_block = (
                        "\n\n## 历史已公开事实（抽 5 条做回归校验）\n" + bullets
                    )
            except Exception:  # noqa: BLE001 - 长程审计永不阻断主流程
                long_range_block = ""

        # Sprint 17-D：注入「截至当前章已登场角色清单」用于 character_too_early 校验
        already_debuted_block = ""
        try:
            chars = list(
                await CharacterRepository(session).list(
                    organization_id=organization_id,
                    project_id=project_id,
                )
            )
            debuted: list[str] = []
            future_only: list[str] = []
            unset: list[str] = []
            for c in chars:
                if not c.name:
                    continue
                chap = getattr(c, "first_appearance_chapter", None)
                if not isinstance(chap, int):
                    unset.append(c.name)
                elif chap <= chapter.chapter_index:
                    debuted.append(f"{c.name}(第{chap}章)")
                else:
                    future_only.append(f"{c.name}(第{chap}章)")
            if debuted or future_only:
                lines = ["\n\n## 截至当前章已登场角色清单"]
                if debuted:
                    lines.append("已可出场：" + "、".join(debuted))
                if future_only:
                    lines.append("尚未到登场时机（禁止出现）：" + "、".join(future_only))
                if unset:
                    lines.append(
                        "登场章节未设置（不参与 character_too_early 判定）：" + "、".join(unset)
                    )
                already_debuted_block = "\n".join(lines)
        except Exception:  # noqa: BLE001
            already_debuted_block = ""

        task_lines = [
            "请审查上述正文是否违反以下任一类约束，并给出可立刻执行的修复建议：",
            "- continuity：是否与故事圣经、之前 scenes 摘要存在情节/时间冲突",
            "- character：人物动机、性格、弧光是否被违反",
            "- world_rule：是否违反世界硬规则",
            "- style：是否偏离风格守则",
            "- cross_chapter：是否承接上一章遗留（open plot_threads 中的悬念"
            "是否被本章合理推进或显式悬置；前一章结尾出现的关键道具/人物/未完成动作"
            "是否被本章首段承接；若道具数量/位置/状态与上一章末尾矛盾即报）",
            "- temporal_continuity：是否与上下文「故事时间」段提供的当前日偏移/时段一致；"
            "未交代过夜的隔日切换、无闪回标注的时间倒退、明显季节矛盾均应报告",
            "- pacing：本章正文情感强度与场面密度是否符合上下文「本章节奏」段提供的"
            "pacing_type / emotion_intensity（climax 章不应通篇内心独白；"
            "cool_down 章不应再起激烈对抗；emotion_intensity=2 章不应出现高强度场面）",
            f"- 统一字数预算：本场持久化/规则预算目标约 {scene_target_words} 字；"
            f"当前正文估算约 {draft_word_count} 字；"
            "允许上下浮动 20%。字数预算是软目标，不属于连续性错误；"
            "只有超长已经造成剧情功能缺失、节奏严重失衡或明显挤占后续必要场景时，"
            "才可作为 pacing 问题提示，并说明具体受影响的剧情功能",
            "- intra_chapter_continuity：本场是否承接同章前序场（参考上下文"
            "「本章前序场已发生」段）；是否漏接前序场留下的钩子、重复了前序场"
            "已用的标志性动作/道具/揭示、人物语气/状态与同章前场是否矛盾、"
            "过渡到本场的方式（时间/地点/视角切换）是否自然；若上下文未提供"
            "该段（即本场是章首），不要报告 intra_chapter_continuity",
            "- character_too_early：本场正文中实际参与剧情的角色（作为对白主语 / "
            "动作主体 / 视角主体 / 场景描写主体出现）必须全部在「截至当前章已登场角色清单」"
            "的「已可出场」列表内。出现「尚未到登场时机」列表里的角色即报，severity=high。"
            "仅作\"路过/远远看见/被名字提及\"的不算实际出场，需判断是否构成\"参与剧情\"。"
            "如果上下文未提供该清单段，不要报告 character_too_early",
            "- state_conflict：正文与「防遗忘审稿清单」里的关键状态项直接矛盾，"
            "例如已获得/已失效/已损坏/已隐藏/已暴露状态被写反",
            "- forgotten_state：正文遗漏本章承接要求或必须持续记住的关键状态；"
            "只有清单或场景任务明确要求本场承接时才报告，不要凭空要求所有状态都出现",
            "- premature_state_use：正文提前使用清单中尚未获得、尚未公开、未到时机的技能、"
            "法宝、身份、情报或伏笔",
            "- resolved_state_reused：正文把已解决、已消耗、已失效或已损坏的状态继续当作可用资源",
            "- hard_constraint_violation：正文违反清单中标记为[硬约束]的状态项或故事圣经硬规则；"
            "此类问题通常 severity=high",
        ]
        if mode == "long_range":
            task_lines.append(
                "- long_range_continuity：本章正文是否与上方「历史已公开事实」"
                "中任一条直接矛盾（仅基于上方明示事实，不要凭空推测）"
            )
        task_lines.append(
            "对每条问题给出 severity (low/medium/high)、description（一句话）、"
            "suggested_fix（一句话）；正文若整体没问题，issues 返回空数组。"
            "只返回 JSON。"
        )

        user_prompt = (
            ctx.to_prompt()
            + "\n\n## 待审稿正文\n"
            + draft_content
            + long_range_block
            + already_debuted_block
            + anti_forgetting_block
            + "\n\n## 任务指令\n"
            + "\n".join(task_lines)
        )
        raw = await model_gateway.generate_json(
            session,
            organization_id=organization_id,
            project_id=project_id,
            job_id=job_id,
            task_type="audit_scene",
            system_prompt=prompt,
            user_prompt=user_prompt,
            schema=AuditResultContract.model_json_schema(),
            prompt_key=_PROMPT_AUDIT_SCENE,
            prompt_version=_PROMPT_VERSION,
            metadata={
                "scene_id": scene.id,
                "chapter_id": chapter.id,
                "context_total_tokens": ctx.total_tokens,
                "audit_mode": mode,
                "scene_target_words": scene_target_words,
                "draft_word_count": draft_word_count,
                **anti_forgetting_meta,
            },
        )
        return AuditResultContract.model_validate(raw)


async def _resolve_audit_scene_target_words(
    session: AsyncSession,
    *,
    organization_id: str,
    chapter: Chapter,
    scene: Scene,
) -> int:
    try:
        stored = int(getattr(scene, "target_words", 0) or 0)
    except (TypeError, ValueError):
        stored = 0
    if stored > 0:
        return stored
    rows = list(
        (
            await session.execute(
                select(Scene.id, Scene.scene_index)
                .where(
                    Scene.organization_id == organization_id,
                    Scene.chapter_id == chapter.id,
                )
                .order_by(Scene.scene_index.asc())
            )
        ).all()
    )
    scene_indices = [row[1] for row in rows]
    total = len(scene_indices) or len(list(chapter.scene_beats or [])) or 1
    position = (
        scene_indices.index(scene.scene_index) + 1
        if scene.scene_index in scene_indices
        else max(1, int(scene.scene_index or 1))
    )
    fallback = max(600, int((chapter.target_words or 0) / max(1, total)) or 1200)
    plan = build_scene_budget_plan(
        chapter=chapter,
        forced_scene_count=total,
        fallback_scene_words=fallback,
    )
    return plan.target_for_scene(position, fallback)


auditor_service = AuditorService()
