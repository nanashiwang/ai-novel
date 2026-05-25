"""生成前检查服务。

把"用户能不能点这个生成按钮"这件事从前端硬编码搬到后端单一真相源：
- 套餐 / 剩余额度是否足够本次操作
- 项目目标章节数是否触发"长篇模式"风险提示
- 当前阶段允许的下一个动作 + 推荐 CTA

任意调用方（Bible 页 / Outline 页 / Write 页）都可以拉一次 preflight，
渲染统一的检查卡片。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import TenantContext
from app.models.project import Project
from app.repositories import QuotaBalanceRepository
from app.services.entitlement.service import PLAN_ENTITLEMENTS, has_entitlement
from app.services.quota.service import _resolve_plan_limit

# 各 job_type 的默认预估消耗字数（与 generation_service 默认值对齐）
DEFAULT_ESTIMATE_WORDS: dict[str, int] = {
    "generate_bible": 2000,
    "revision_rewrite_proposal": 3000,
    "generate_outline": 3000,
    "generate_scene_plan": 1500,
    "write_scene": 4000,
    "audit_scene": 800,
    "rewrite_scene": 4000,
    "full_novel": 20000,
}

# job_type → 对应的 entitlement key。generation_service 中调
# require_entitlement 的位置必须与本表保持一致。
JOB_ENTITLEMENT: dict[str, str] = {
    "revision_rewrite_proposal": "generation:chapter",
    "write_scene": "generation:scene",
    "rewrite_scene": "generation:scene",
    "full_novel": "generation:full_novel",
}

# 长篇模式阈值：>= 这个数视为"超长篇"，提示用户分批策略
LONG_NOVEL_CHAPTER_THRESHOLD = 200


@dataclass
class CheckItem:
    """单条检查项。level=ok/warn/block；block 阻止生成。"""

    label: str
    level: Literal["ok", "warn", "block"]
    detail: str = ""


@dataclass
class PreflightReport:
    project_status: str
    plan_code: str
    quota_key: str
    quota_limit: int  # 套餐档位限额（来自 plan_features）；为 None 表示套餐没有该额度
    quota_used: int
    quota_reserved: int
    quota_available: int  # limit - used - reserved
    estimate_words: int
    target_chapter_count: int
    is_long_novel: bool
    can_generate: bool
    checks: list[CheckItem] = field(default_factory=list)
    next_action: dict | None = None  # {"kind": ..., "label": ..., "href_suffix": ...}

    def as_dict(self) -> dict:
        return {**asdict(self), "checks": [asdict(c) for c in self.checks]}


# project.status → 推荐下一动作（label + 目标路径后缀 + 对应 job_type）
_NEXT_ACTIONS: dict[str, dict] = {
    "created": {
        "kind": "generate_bible",
        "label": "生成故事圣经",
        "href_suffix": "/bible",
    },
    "bible_generating": {
        "kind": "wait",
        "label": "查看任务进度",
        "href_suffix": "/jobs",
    },
    "bible_ready": {
        "kind": "generate_outline",
        "label": "生成章节大纲",
        "href_suffix": "/outline",
    },
    "outline_generating": {
        "kind": "wait",
        "label": "查看任务进度",
        "href_suffix": "/jobs",
    },
    "outlined": {
        "kind": "generate_scene_plan",
        "label": "拆分第 1 章场景",
        "href_suffix": "/outline",
    },
    "scenes_planning": {
        "kind": "wait",
        "label": "查看任务进度",
        "href_suffix": "/jobs",
    },
    "scenes_planned": {
        "kind": "write_scene",
        "label": "生成第 1 个场景",
        "href_suffix": "/write",
    },
    "drafting": {
        "kind": "write_scene",
        "label": "继续生成下一章",
        "href_suffix": "/write",
    },
    "completed": {
        "kind": "export",
        "label": "导出全书",
        "href_suffix": "/export",
    },
}


class PreflightService:
    QUOTA_KEY = "monthly_generated_words"

    async def check(
        self,
        session: AsyncSession,
        tenant: TenantContext,
        project: Project,
        *,
        job_type: str,
    ) -> PreflightReport:
        estimate = DEFAULT_ESTIMATE_WORDS.get(job_type, 2000)

        # 1) 套餐额度数据
        plan_limit = await _resolve_plan_limit(session, tenant.plan_code, self.QUOTA_KEY)
        balance_repo = QuotaBalanceRepository(session)
        balance = await balance_repo.get_for_update(
            organization_id=tenant.organization_id,
            quota_key=self.QUOTA_KEY,
        )
        # quota_limit 真相源优先级：balance（实际配额行）> plan_features > 0
        quota_limit = int(
            balance.limit_value if balance else (plan_limit if plan_limit is not None else 0)
        )
        quota_used = int(balance.used_value if balance else 0)
        quota_reserved = int(balance.reserved_value if balance else 0)
        quota_available = max(0, quota_limit - quota_used - quota_reserved)

        checks: list[CheckItem] = []

        # 2) 套餐 / 额度检查
        # 只有当组织 *既* 没有 balance 行 *又* 套餐里没配置此 quota 时，才视为
        # "套餐未覆盖"——避免新建组织在首次 reserve 之前都被误判 block。
        if not balance and plan_limit is None:
            checks.append(
                CheckItem(
                    label="套餐未覆盖此功能",
                    level="block",
                    detail=f"当前套餐 {tenant.plan_code} 没有 {self.QUOTA_KEY} 额度。",
                )
            )
        elif quota_available < estimate:
            checks.append(
                CheckItem(
                    label="本月剩余额度不足以完成本次生成",
                    level="block",
                    detail=(
                        f"本次预估消耗 {estimate} 字，剩余 {quota_available} 字。"
                        " 请升级套餐或等待下月重置。"
                    ),
                )
            )
        else:
            checks.append(
                CheckItem(
                    label="额度充足",
                    level="ok",
                    detail=(
                        f"本次预估消耗 {estimate} 字，剩余 {quota_available} 字。"
                    ),
                )
            )

        # 3) 超长篇风险提示（不阻断，只 warn）
        is_long_novel = project.target_chapter_count >= LONG_NOVEL_CHAPTER_THRESHOLD
        if is_long_novel:
            # 粗估全书生成需要的字数 = 目标字数 × 1.2 倍（含审稿 / 重写）
            est_total = max(project.target_word_count, 1) * 1.2
            checks.append(
                CheckItem(
                    label=f"超长篇模式（{project.target_chapter_count} 章）",
                    level="warn",
                    detail=(
                        f"完整生成预计需要约 {int(est_total)} 字额度"
                        f"（≈ {int(est_total / 10000)} 万）。"
                        " 建议采用分批策略：先生成圣经 + 前 3 章试写，确认风格后再批量生成；"
                        " 每 10 章做一次记忆校准，每 50 章做一次主线复盘。"
                    ),
                )
            )

        # 4) 状态机：当前 status 是否允许生成此 job_type
        status_blocker = self._status_blocker(project.status, job_type)
        if status_blocker:
            checks.append(status_blocker)

        # 5) entitlement 检查（套餐档位是否解锁此功能入口）
        ent_key = JOB_ENTITLEMENT.get(job_type)
        if ent_key and not has_entitlement(tenant, ent_key):
            # 找出最低能用此 entitlement 的套餐，给升级方向
            upgradable = [
                code
                for code, ents in PLAN_ENTITLEMENTS.items()
                if "*" in ents or ent_key in ents
            ]
            checks.append(
                CheckItem(
                    label="当前套餐未解锁此功能",
                    level="block",
                    detail=(
                        f"当前 {tenant.plan_code} 套餐没有 {ent_key} 权限。"
                        + (f" 可升级到：{' / '.join(upgradable)}。" if upgradable else "")
                    ),
                )
            )

        can_generate = not any(c.level == "block" for c in checks)

        next_action = _NEXT_ACTIONS.get(project.status)

        return PreflightReport(
            project_status=project.status,
            plan_code=tenant.plan_code,
            quota_key=self.QUOTA_KEY,
            quota_limit=quota_limit,
            quota_used=quota_used,
            quota_reserved=quota_reserved,
            quota_available=quota_available,
            estimate_words=estimate,
            target_chapter_count=project.target_chapter_count,
            is_long_novel=is_long_novel,
            can_generate=can_generate,
            checks=checks,
            next_action=next_action,
        )

    @staticmethod
    def _status_blocker(status: str, job_type: str) -> CheckItem | None:
        """根据当前 status 判断 job_type 是否被状态机允许。

        只列出明显矛盾的组合，其余视为允许。本检查是"防呆"而非"严格状态机"，
        真正的状态守卫仍由 activities 层执行。
        """
        if job_type == "generate_outline" and status in {"created", "bible_generating"}:
            return CheckItem(
                label="需要先完成故事圣经",
                level="block",
                detail="还没有 NovelSpec。请先点「生成故事圣经」。",
            )
        if job_type == "generate_scene_plan" and status in {
            "created",
            "bible_generating",
            "bible_ready",
            "outline_generating",
        }:
            return CheckItem(
                label="需要先完成章节大纲",
                level="block",
                detail="还没有 chapters。请先点「生成大纲」。",
            )
        return None


preflight_service = PreflightService()
