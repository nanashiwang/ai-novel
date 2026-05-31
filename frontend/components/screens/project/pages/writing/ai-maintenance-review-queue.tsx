"use client";

import { AlertTriangle, Bot, CheckCircle2, MapPin } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type {
  Chapter,
  StoryStateItem,
  StoryStateMaintenanceAction,
} from "@/lib/api";

const actionLabel: Record<StoryStateMaintenanceAction["action_type"], string> = {
  update_state: "更新设定",
  merge_states: "合并设定",
  supersede_state: "替代设定",
  create_requirement: "新增承接",
  resolve_requirement: "解决承接",
  supersede_requirement: "替代承接",
};

const statusLabel: Record<StoryStateMaintenanceAction["status"], string> = {
  applied: "已应用",
  needs_review: "待确认",
  suggested: "仅建议",
  skipped: "已跳过",
  rolled_back: "已撤销",
};

const statusTone: Record<
  StoryStateMaintenanceAction["status"],
  "slate" | "blue" | "green" | "amber" | "rose"
> = {
  applied: "green",
  needs_review: "amber",
  suggested: "blue",
  skipped: "slate",
  rolled_back: "rose",
};

const riskTone: Record<StoryStateMaintenanceAction["risk_level"], "green" | "amber" | "rose"> = {
  low: "green",
  medium: "amber",
  high: "rose",
};

type AIMaintenanceReviewQueueProps = {
  actions: StoryStateMaintenanceAction[];
  chapters: Chapter[];
  isPending?: boolean;
  applyingActionId?: string | null;
  storyStateById: Record<string, StoryStateItem>;
  onSelectState: (state: StoryStateItem) => void;
  onApplyAction: (actionId: string) => void;
  onFocusAction?: (action: StoryStateMaintenanceAction) => void;
};

export function AIMaintenanceReviewQueue({
  actions,
  chapters,
  isPending,
  applyingActionId,
  storyStateById,
  onSelectState,
  onApplyAction,
  onFocusAction,
}: AIMaintenanceReviewQueueProps) {
  const needsReviewCount = actions.filter((item) => item.status === "needs_review").length;
  const suggestedCount = actions.filter((item) => item.status === "suggested").length;

  return (
    <Card className="border-amber-100 bg-gradient-to-br from-amber-50 via-white to-cyan-50">
      <CardHeader className="flex flex-row items-center justify-between gap-3 pb-3">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <span className="grid size-7 place-items-center rounded-xl bg-amber-500 text-white shadow-sm">
              <Bot className="size-4" />
            </span>
            AI 维护待确认
          </CardTitle>
          <p className="mt-1 text-[11px] text-slate-500">
            聚合整个项目需要你确认的关键设定维护动作
          </p>
        </div>
        {isPending ? <Badge tone="blue">读取中</Badge> : <Badge tone="amber">{actions.length}</Badge>}
      </CardHeader>
      <CardContent className="space-y-3">
        {actions.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {needsReviewCount ? <Badge tone="amber">待确认 {needsReviewCount}</Badge> : null}
            {suggestedCount ? <Badge tone="blue">仅建议 {suggestedCount}</Badge> : null}
          </div>
        ) : null}

        {actions.length === 0 ? (
          <div className="rounded-xl border border-dashed border-amber-200 bg-white/70 px-3 py-3 text-xs leading-5 text-slate-500">
            {isPending
              ? "正在读取 AI 维护待确认队列。"
              : "当前没有待确认的 AI 维护建议。低风险动作会自动应用，高风险/低置信动作会出现在这里。"}
          </div>
        ) : (
          <ul className="space-y-2">
            {actions.slice(0, 8).map((action) => {
              const targetState = action.target_state_id
                ? storyStateById[action.target_state_id]
                : null;
              const chapter = action.chapter_id
                ? chapters.find((item) => item.id === action.chapter_id)
                : null;
              const isApplying = applyingActionId === action.id;
              return (
                <li
                  key={action.id}
                  className="rounded-xl border border-white/80 bg-white/85 p-3 text-xs shadow-sm"
                >
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone={statusTone[action.status]}>{statusLabel[action.status]}</Badge>
                    <Badge tone="slate">{actionLabel[action.action_type]}</Badge>
                    <Badge tone={riskTone[action.risk_level]}>风险 {action.risk_level}</Badge>
                    <Badge tone="blue">置信 {Math.round(action.confidence * 100)}%</Badge>
                  </div>
                  <div className="mt-2 flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" />
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold leading-5 text-slate-950">
                        {action.reason || "AI 发现一条待确认的关键设定维护动作"}
                      </p>
                      <p className="mt-1 text-[11px] text-slate-500">
                        {chapter
                          ? `第 ${chapter.chapter_index} 章 · ${chapter.title}`
                          : action.chapter_id
                            ? `章节 ${action.chapter_id.slice(0, 12)}…`
                            : "项目级维护建议"}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {targetState ? (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 px-2 text-[11px]"
                            onClick={() => onSelectState(targetState)}
                          >
                            查看设定：{targetState.name}
                          </Button>
                        ) : null}
                        {onFocusAction && action.chapter_id ? (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 px-2 text-[11px] text-slate-600 hover:bg-slate-100"
                            onClick={() => onFocusAction(action)}
                          >
                            <MapPin className="size-3.5" />
                            定位来源
                          </Button>
                        ) : null}
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 px-2 text-[11px] text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800"
                          disabled={isApplying}
                          onClick={() => {
                            if (
                              window.confirm(
                                "确定应用这条 AI 维护建议吗？系统会按记录的 patch 修改关键设定/承接要求。",
                              )
                            ) {
                              onApplyAction(action.id);
                            }
                          }}
                        >
                          <CheckCircle2 className="size-3.5" />
                          {isApplying ? "应用中" : "确认应用"}
                        </Button>
                      </div>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {actions.length > 8 ? (
          <p className="text-[11px] text-slate-500">
            仅展示最近 8 条，更多待确认动作可后续进入独立维护队列页。
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
