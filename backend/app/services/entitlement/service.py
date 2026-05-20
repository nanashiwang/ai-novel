from fastapi import HTTPException, status

from app.core.tenancy import TenantContext

# 套餐 entitlements 设计原则：
# - 成本控制由 monthly_generated_words / monthly_review_count 等额度承担
# - entitlement 只用来标记"是否允许使用这类功能的整体入口"
# - Free 也允许走通完整生成链（圣经 → 大纲 → 场景计划 → 场景写作 →
#   审稿 → 重写 → 导出），以字数额度限制总量。这样新用户能直接体验全
#   流程，升级动机来自"想跑得更多"而非"被功能墙挡死"
# - 仅 full_novel（一次性跑全书 pipeline）保留付费门槛，避免 Free 一次
#   性耗光额度
PLAN_ENTITLEMENTS: dict[str, set[str]] = {
    "Free": {
        "project:create",
        "generation:chapter",
        "generation:scene",
        "audit:advanced",
        "rewrite:advanced",
        "export_markdown",
        "export_txt",
    },
    "Starter": {
        "project:create",
        "generation:chapter",
        "generation:scene",
        "audit:advanced",
        "rewrite:advanced",
        "memory:advanced",
        "export_markdown",
        "export_txt",
        "export_docx",
    },
    "Pro": {
        "project:create",
        "generation:full_novel",
        "generation:chapter",
        "generation:scene",
        "audit:advanced",
        "rewrite:advanced",
        "memory:advanced",
        "export_markdown",
        "export_txt",
        "export_docx",
        "export_epub",
        "export_pdf",
    },
    "Team": {"*"},
    "Enterprise": {"*"},
}


def require_entitlement(tenant: TenantContext, entitlement_key: str) -> None:
    entitlements = PLAN_ENTITLEMENTS.get(tenant.plan_code, set())
    if "*" not in entitlements and entitlement_key not in entitlements:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="entitlement_required",
        )


def has_entitlement(tenant: TenantContext, entitlement_key: str) -> bool:
    """非抛错版本：用于 preflight 一类只读检查。"""
    entitlements = PLAN_ENTITLEMENTS.get(tenant.plan_code, set())
    return "*" in entitlements or entitlement_key in entitlements
