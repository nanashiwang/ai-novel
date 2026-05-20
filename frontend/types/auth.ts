export type PlatformRole = "user" | "operator" | "support" | "finance_admin" | "admin" | "super_admin";
export type OrganizationRole = "owner" | "admin" | "editor" | "viewer" | "billing_manager" | "member";
export type UserStatus = "active" | "suspended" | "deleted";
export type PlanCode = "Free" | "Starter" | "Pro" | "Team" | "Enterprise" | "Internal";

export type FrontendUser = {
  id: string;
  name: string;
  email: string;
  platformRole: PlatformRole;
  organizationRole: OrganizationRole;
  status: UserStatus;
  currentOrganizationId: string;
  organizationName: string;
  planCode: PlanCode;
};

export type Organization = {
  id: string;
  name: string;
  ownerUserId: string;
  planCode: PlanCode;
  status: "active" | "suspended" | "trialing" | "cancelled";
  createdAt: string;
};

export type OrganizationMember = {
  id: string;
  organizationId: string;
  userId: string;
  role: OrganizationRole;
  status: "active" | "invited" | "removed";
  joinedAt: string;
};
