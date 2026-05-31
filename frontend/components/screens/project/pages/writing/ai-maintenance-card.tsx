"use client";

import { Bot, GitMerge, ShieldAlert, WandSparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type {
  StoryStateItem,
  StoryStateMaintenanceAction,
  StoryStateMaintenanceRiskLevel,
  StoryStateMaintenanceStatus,
} from "@/lib/api";

const actionLabel: Record<StoryStateMaintenanceAction["action_type"], string> = {
  update_state: "更新设定",
  merge_states: "合并设定",
  resolve_requirement: "解决承接",
  supersede_requirement: "替代承接",
};

const statusLabel: Record<StoryStateMaintenanceStatus, string> = {
  applied: "已自动应用",
  needs_review: "待确认",
  suggested: "仅建议",
  skipped: "已跳过",
  rolled_back: "已回滚",
};

const statusTone: Record<StoryStateMaintenanceStatus, "slate" | "blue" | "green" | "amber" | "rose"> = {
  applied: "green",
  needs_review: "amber",
  suggested: "blue",
  skipped: "slate",
  rolled_back: "rose",
};

const riskTone: Record<StoryStateMaintenanceRiskLevel, "green" | "amber" | "rose"> = {
  low: "green",
  medium: "amber",
  high: "rose",
};

type AIMaintenanceCardProps = {
  actions: StoryStateMaintenanceAction[];
  isPending?: boolean;
  storyStateById: Record<string, StoryStateItem>;
  onSelectState: (state: StoryStateItem) => void;
};

export function AIMaintenanceCard({
  actions,
  isPending,
  storyStateById,
  onSelectState,
}: AIMaintenanceCardProps) {
  const applied = actions.filter((item) => item.status === "applied").length;
  const needsReview = actions.filter((item) => item.status === "needs_review").length;
  const suggested = actions.filter((item) => item.status === "suggested").length;
  const skipped = actions.filter((item) => item.status === "skipped").length;

  return (
    <div className="rounded-2xl border border-cyan-100 bg-gradient-to-br from-cyan-50 via-white to-slate-50 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="grid size-7 place-items-center rounded-xl bg-cyan-600 text-white shadow-sm">
              <Bot className="size-4" />
            </span>
            <div>
              <p className="text-sm font-black text-slate-950">AI 维护结果</p>
              <p className="text-[11px] text-slate-500">
                生成/重写后自动维护关键设定
              </p>
            </div>
          </div>
        </div>
        {isPending ? <Badge tone="blue">读取中</Badge> : <Badge tone="slate">{actions.length}</Badge>}
      </div>

      {actions.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {applied ? <Badge tone="green">自动应用 {applied}</Badge> : null}
          {needsReview ? <Badge tone="amber">待确认 {needsReview}</Badge> : null}
          {suggested ? <Badge tone="blue">建议 {suggested}</Badge> : null}
          {skipped ? <Badge tone="slate">跳过 {skipped}</Badge> : null}
        </div>
      ) : null}

      {actions.length === 0 ? (
        <div className="mt-3 rounded-xl border border-dashed border-cyan-200 bg-white/70 px-3 py-3 text-xs leading-5 text-slate-500">
          {isPending
            ? "正在读取维护记录。"
            : "当前场景暂无 AI 维护记录。生成或重写正文后，如果有关键设定变化，会显示在这里。"}
        </div>
      ) : (
        <ul className="mt-3 space-y-2">
          {actions.slice(0, 6).map((action) => (
            <AIMaintenanceActionItem
              key={action.id}
              action={action}
              storyStateById={storyStateById}
              onSelectState={onSelectState}
            />
          ))}
        </ul>
      )}

      {actions.length > 6 ? (
        <p className="mt-2 text-[11px] text-slate-500">
          仅展示最近 6 条，更多记录已保留在维护日志中。
        </p>
      ) : null}
    </div>
  );
}

function AIMaintenanceActionItem({
  action,
  storyStateById,
  onSelectState,
}: {
  action: StoryStateMaintenanceAction;
  storyStateById: Record<string, StoryStateItem>;
  onSelectState: (state: StoryStateItem) => void;
}) {
  const targetState = action.target_state_id
    ? storyStateById[action.target_state_id]
    : null;
  const beforeSummary = findSummary(action.before_json);
  const afterSummary = findSummary(action.after_json);
  const impactText = buildImpactText(action);

  return (
    <li className="rounded-xl border border-white/80 bg-white/85 p-3 text-xs shadow-sm">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone={statusTone[action.status]}>{statusLabel[action.status]}</Badge>
        <Badge tone="slate">{actionLabel[action.action_type]}</Badge>
        <Badge tone={riskTone[action.risk_level]}>风险 {action.risk_level}</Badge>
        <Badge tone="blue">置信 {Math.round(action.confidence * 100)}%</Badge>
      </div>
      <div className="mt-2 flex items-start gap-2">
        {action.action_type === "merge_states" ? (
          <GitMerge className="mt-0.5 size-4 shrink-0 text-cyan-600" />
        ) : action.status === "needs_review" ? (
          <ShieldAlert className="mt-0.5 size-4 shrink-0 text-amber-600" />
        ) : (
          <WandSparkles className="mt-0.5 size-4 shrink-0 text-cyan-600" />
        )}
        <div className="min-w-0 flex-1">
          <p className="font-semibold leading-5 text-slate-900">
            {action.reason || "AI 已记录一条关键设定维护动作"}
          </p>
          {impactText ? (
            <p className="mt-1 text-[11px] text-slate-500">{impactText}</p>
          ) : null}
          {targetState ? (
            <Button
              size="sm"
              variant="ghost"
              className="mt-2 h-7 px-2 text-[11px]"
              onClick={() => onSelectState(targetState)}
            >
              查看关键设定：{targetState.name}
            </Button>
          ) : null}
        </div>
      </div>
      {beforeSummary || afterSummary ? (
        <div className="mt-2 grid gap-2 rounded-lg bg-slate-50 p-2 text-[11px] leading-5 text-slate-600">
          {beforeSummary ? (
            <p>
              <span className="font-bold text-slate-700">改前：</span>
              {beforeSummary}
            </p>
          ) : null}
          {afterSummary && afterSummary !== beforeSummary ? (
            <p>
              <span className="font-bold text-slate-700">改后：</span>
              {afterSummary}
            </p>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

function findSummary(value: Record<string, unknown>) {
  const targetSummary = readPath(value, ["target", "summary"]);
  if (targetSummary) return targetSummary;
  const requirementSummary = readPath(value, ["requirement", "summary"]);
  if (requirementSummary) {
    const status = readPath(value, ["requirement", "status"]);
    return status ? `${requirementSummary}（${status}）` : requirementSummary;
  }
  const firstSource = readPath(value, ["sources", "0", "summary"]);
  if (firstSource) return firstSource;
  return "";
}

function buildImpactText(action: StoryStateMaintenanceAction) {
  const requirementCount = readNumber(action.after_json, "updated_requirement_count");
  const issueCount = readNumber(action.after_json, "updated_issue_count");
  const parts = [];
  if (action.source_state_ids.length > 0) {
    parts.push(`来源设定 ${action.source_state_ids.length} 条`);
  }
  if (requirementCount) {
    parts.push(`回连承接要求 ${requirementCount} 条`);
  }
  if (issueCount) {
    parts.push(`回连审稿问题 ${issueCount} 条`);
  }
  if (action.target_requirement_id && action.action_type !== "merge_states") {
    parts.push(`承接要求 ${action.target_requirement_id.slice(0, 12)}…`);
  }
  return parts.join(" · ");
}

function readPath(value: unknown, path: string[]) {
  let current: unknown = value;
  for (const key of path) {
    if (Array.isArray(current)) {
      const index = Number(key);
      current = Number.isNaN(index) ? undefined : current[index];
      continue;
    }
    if (!current || typeof current !== "object") return "";
    current = (current as Record<string, unknown>)[key];
  }
  return typeof current === "string" ? current : "";
}

function readNumber(value: Record<string, unknown>, key: string) {
  const raw = value[key];
  return typeof raw === "number" ? raw : 0;
}
