import type { StoryStateMaintenanceAction } from "@/lib/api";

type BadgeTone = "slate" | "blue" | "green" | "amber" | "rose" | "violet" | "orange";

type AutoDecision = {
  policy?: string;
  auto_applied?: boolean;
  rollback_supported?: boolean;
  threshold?: number | null;
  reason?: string;
};

type DecisionBadge = {
  label: string;
  tone: BadgeTone;
};

const decisionBadgeByPolicy: Record<string, DecisionBadge> = {
  high_risk_needs_review: { label: "高风险确认", tone: "rose" },
  low_confidence_suggested: { label: "低置信建议", tone: "blue" },
  low_confidence_below_auto_apply: { label: "仅建议", tone: "blue" },
  low_confident_auto_apply: { label: "低风险自动", tone: "green" },
  medium_confidence_below_auto_apply: { label: "中风险确认", tone: "amber" },
  medium_confident_rollbackable: { label: "中风险自动 · 可撤销", tone: "green" },
  medium_rollback_unsupported: { label: "需确认 · 不可撤销", tone: "amber" },
};

export function getMaintenanceAutoDecision(
  action: StoryStateMaintenanceAction,
): AutoDecision | null {
  const raw = action.patch_json?.auto_decision;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return null;
  }
  return raw as AutoDecision;
}

export function getMaintenanceDecisionBadge(
  action: StoryStateMaintenanceAction,
): DecisionBadge | null {
  const decision = getMaintenanceAutoDecision(action);
  const policy = typeof decision?.policy === "string" ? decision.policy : "";
  return decisionBadgeByPolicy[policy] ?? null;
}

export function getMaintenanceDecisionHint(action: StoryStateMaintenanceAction) {
  const decision = getMaintenanceAutoDecision(action);
  const policy = typeof decision?.policy === "string" ? decision.policy : "";
  if (policy === "medium_confident_rollbackable") {
    return "AI 判定：中风险高置信且支持撤销，已自动应用；如判断不合适，可点“撤销”恢复。";
  }
  if (policy === "medium_rollback_unsupported") {
    return "AI 判定：中风险但该动作暂不支持撤销，因此进入人工确认。";
  }
  if (policy === "medium_confidence_below_auto_apply") {
    return "AI 判定：中风险置信度未达到自动应用阈值，因此进入人工确认。";
  }
  if (policy === "low_confidence_suggested") {
    return "AI 判定：置信度较低，仅记录为建议，不直接修改设定库。";
  }
  if (policy === "high_risk_needs_review") {
    return "AI 判定：高风险动作必须人工确认，不自动改库。";
  }
  return "";
}
