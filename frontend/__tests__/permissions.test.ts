import { describe, expect, it } from "vitest";

import {
  canManageBilling,
  canManageOrganization,
  canWriteProject,
  isPlatformAdmin,
  isSuperAdmin,
} from "@/lib/permissions";

import type { CurrentUser } from "@/lib/api";

function makeUser(overrides: Partial<CurrentUser> = {}): CurrentUser {
  return {
    id: "u1",
    email: "u1@example.com",
    display_name: "U1",
    platform_role: "user",
    organization_role: "viewer",
    organization_id: "o1",
    organization_name: "o1",
    plan_code: "Free",
    ...overrides,
  };
}

describe("permissions", () => {
  it("isPlatformAdmin returns false for normal user", () => {
    expect(isPlatformAdmin(makeUser())).toBe(false);
    expect(isPlatformAdmin(null)).toBe(false);
  });

  it("isPlatformAdmin / isSuperAdmin recognize admin roles", () => {
    expect(isPlatformAdmin(makeUser({ platform_role: "admin" }))).toBe(true);
    expect(isPlatformAdmin(makeUser({ platform_role: "super_admin" }))).toBe(true);
    expect(isSuperAdmin(makeUser({ platform_role: "super_admin" }))).toBe(true);
    expect(isSuperAdmin(makeUser({ platform_role: "admin" }))).toBe(false);
  });

  it("canManageBilling honors organization_role", () => {
    expect(canManageBilling(makeUser({ organization_role: "owner" }))).toBe(true);
    expect(canManageBilling(makeUser({ organization_role: "billing_manager" }))).toBe(true);
    expect(canManageBilling(makeUser({ organization_role: "editor" }))).toBe(false);
  });

  it("canManageOrganization is owner/admin only", () => {
    expect(canManageOrganization(makeUser({ organization_role: "owner" }))).toBe(true);
    expect(canManageOrganization(makeUser({ organization_role: "editor" }))).toBe(false);
  });

  it("canWriteProject excludes viewer", () => {
    expect(canWriteProject(makeUser({ organization_role: "editor" }))).toBe(true);
    expect(canWriteProject(makeUser({ organization_role: "viewer" }))).toBe(false);
  });
});
