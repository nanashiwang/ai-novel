import type { PlanCode } from "./auth";

export type Plan = {
  code: PlanCode;
  name: string;
  description: string;
  priceMonthly: number;
  priceYearly?: number;
  status: "active" | "archived" | "hidden";
  queuePriority: "low" | "normal" | "high" | "enterprise" | "internal";
  maxConcurrentJobs: number;
  targetUser: string;
};

export type PlanFeature = {
  id: string;
  planCode: PlanCode;
  featureKey: string;
  featureName: string;
  enabled: boolean;
  limitValue: number | "unlimited";
  limitUnit: "words" | "times" | "projects" | "members" | "formats" | "GB" | "level" | "boolean";
  description: string;
};

export type QuotaKey =
  | "monthly_generated_words"
  | "monthly_review_count"
  | "monthly_rewrite_count"
  | "max_projects"
  | "team_members"
  | "concurrent_jobs"
  | "export_docx"
  | "export_epub";

export type QuotaBalance = {
  id: string;
  organizationId: string;
  quotaKey: QuotaKey;
  label: string;
  periodStart: string;
  periodEnd: string;
  limitValue: number;
  usedValue: number;
  reservedValue: number;
  resetAt: string;
};

export type QuotaReservation = {
  id: string;
  organizationId: string;
  generationJobId: string;
  quotaKey: QuotaKey;
  reservedAmount: number;
  consumedAmount: number;
  status: "reserved" | "settled" | "released" | "expired";
  createdAt: string;
  updatedAt: string;
};

export type UsageEvent = {
  id: string;
  organizationId: string;
  userId: string;
  projectId?: string;
  generationJobId?: string;
  eventType: "generate_words" | "review" | "rewrite" | "export" | "manual_adjustment";
  amount: number;
  unit: "words" | "times" | "files";
  createdAt: string;
};
