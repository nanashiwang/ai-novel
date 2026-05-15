from fastapi import HTTPException, status
from app.core.tenancy import TenantContext

PLAN_ENTITLEMENTS: dict[str, set[str]] = {
    "Free": {"project:create", "export_markdown", "export_txt"},
    "Starter": {"project:create", "generation:chapter", "export_markdown", "export_txt", "export_docx"},
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
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="entitlement_required")
