import type { CurrentUser } from "./api";

/**
 * 前端权限工具。
 *
 * 字段对齐后端返回的 CurrentUser（snake_case）。
 * 这些函数仅做 UI 层 hint，所有写操作的最终决定权在后端。
 */

export function isPlatformAdmin(user?: CurrentUser | null) {
  return !!user && ["admin", "super_admin"].includes(user.platform_role);
}

export function isSuperAdmin(user?: CurrentUser | null) {
  return user?.platform_role === "super_admin";
}

export function canManageBilling(user?: CurrentUser | null) {
  return !!user && ["owner", "billing_manager"].includes(user.organization_role);
}

export function canManageOrganization(user?: CurrentUser | null) {
  return !!user && ["owner", "admin"].includes(user.organization_role);
}

export function canWriteProject(user?: CurrentUser | null) {
  return !!user && ["owner", "editor"].includes(user.organization_role);
}
