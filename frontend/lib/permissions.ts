import type { MockUser } from "@/types";

export function isPlatformAdmin(user?: MockUser | null) {
  return !!user && ["admin", "super_admin"].includes(user.platformRole);
}

export function isSuperAdmin(user?: MockUser | null) {
  return user?.platformRole === "super_admin";
}

export function canManageBilling(user?: MockUser | null) {
  return !!user && ["owner", "billing_manager"].includes(user.organizationRole);
}
