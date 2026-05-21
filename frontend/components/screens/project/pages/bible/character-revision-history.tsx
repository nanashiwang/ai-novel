"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Loader2, Sparkles, UndoDot, UserRound } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  type CharacterRevisionSource,
  type CharacterRevisionStatus,
  characterRevisionsApi,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { ApiError } from "@/lib/http";
import { useScopedKey } from "@/lib/use-scoped-key";

const sourceLabel: Record<CharacterRevisionSource, string> = {
  user_edit: "手动编辑",
  copilot: "AI 共创",
  ai_inferred: "AI 推演",
};

const statusLabel: Record<CharacterRevisionStatus, string> = {
  pending: "待审核",
  applied: "已应用",
  rejected: "已驳回",
  superseded: "已取代",
};

const fieldLabel: Record<string, string> = {
  name: "姓名",
  role: "定位",
  description: "描述",
  personality: "性格",
  motivation: "动机",
  secret: "秘密",
  arc: "弧光",
  relationships: "人物关系",
  current_state: "当前状态",
};

function formatValue(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value, null, 2);
}

export type CharacterRevisionHistoryProps = {
  projectId: string;
  characterId: string;
  onAfterChange?: () => void;
};

/**
 * 人物字段版本链历史 + 待审核操作面板。
 *
 * 三种来源（手动 / Copilot / AI 推演）落同一条时间轴：
 * - pending 显示「应用 / 驳回」按钮
 * - applied 显示「回滚到此版本」按钮（生成一条新 user_edit + applied 记录）
 * - rejected / superseded 仅展示，不允许操作
 */
export function CharacterRevisionHistory({
  projectId,
  characterId,
  onAfterChange,
}: CharacterRevisionHistoryProps) {
  const queryClient = useQueryClient();
  const charactersKey = useScopedKey("project", projectId, "characters");
  const revisionsKey = useScopedKey(
    "project",
    projectId,
    "character-revisions",
    characterId,
  );
  const pendingKey = useScopedKey(
    "project",
    projectId,
    "character-revisions-pending",
  );

  const { data: revisions = [], isPending } = useQuery({
    queryKey: revisionsKey,
    queryFn: () =>
      characterRevisionsApi.list(projectId, characterId, { limit: 100 }),
  });

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: charactersKey });
    queryClient.invalidateQueries({ queryKey: revisionsKey });
    queryClient.invalidateQueries({ queryKey: pendingKey });
    onAfterChange?.();
  };

  const apply = useMutation({
    mutationFn: (revisionId: string) =>
      characterRevisionsApi.apply(projectId, characterId, revisionId),
    onSuccess: () => {
      toast.success("已应用");
      invalidateAll();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "应用失败"),
  });
  const reject = useMutation({
    mutationFn: (revisionId: string) =>
      characterRevisionsApi.reject(projectId, characterId, revisionId),
    onSuccess: () => {
      toast.success("已驳回");
      invalidateAll();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "驳回失败"),
  });
  const rollback = useMutation({
    mutationFn: (revisionId: string) =>
      characterRevisionsApi.rollback(projectId, characterId, revisionId),
    onSuccess: () => {
      toast.success("已回滚到该版本");
      invalidateAll();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "回滚失败"),
  });

  if (isPending) {
    return <p className="py-6 text-center text-sm text-slate-500">加载历史版本…</p>;
  }
  if (revisions.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-slate-500">
        暂无版本变更记录。手动编辑、Copilot 共创或 AI 推演产生的变化都会列在此处。
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {revisions.map((rev) => {
        const isPendingRev = rev.status === "pending";
        const isAppliedRev = rev.status === "applied";
        return (
          <div
            key={rev.id}
            className={cn(
              "rounded-2xl border p-3 text-sm",
              isPendingRev
                ? "border-amber-200 bg-amber-50/40"
                : isAppliedRev
                  ? "border-emerald-100 bg-white"
                  : "border-slate-200 bg-slate-50",
            )}
          >
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge tone={isPendingRev ? "amber" : isAppliedRev ? "green" : "slate"}>
                {statusLabel[rev.status]}
              </Badge>
              <Badge tone={rev.source === "ai_inferred" ? "violet" : "blue"}>
                {rev.source === "user_edit" ? (
                  <UserRound className="mr-1 inline size-3" />
                ) : rev.source === "ai_inferred" ? (
                  <Sparkles className="mr-1 inline size-3" />
                ) : (
                  <Bot className="mr-1 inline size-3" />
                )}
                {sourceLabel[rev.source]}
              </Badge>
              <span className="font-bold text-slate-800">
                {fieldLabel[rev.field] ?? rev.field}
              </span>
              {rev.applied_at ? (
                <span className="text-slate-400">
                  应用于 {formatDateTime(rev.applied_at)}
                </span>
              ) : rev.created_at ? (
                <span className="text-slate-400">
                  创建于 {formatDateTime(rev.created_at)}
                </span>
              ) : null}
            </div>
            <div className="mt-2 grid gap-1 text-xs md:grid-cols-2">
              <div>
                <p className="font-bold text-slate-500">旧值</p>
                <pre className="mt-1 max-h-28 overflow-y-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-2 text-slate-600">
                  {formatValue(rev.old_value)}
                </pre>
              </div>
              <div>
                <p className="font-bold text-slate-500">新值</p>
                <pre className="mt-1 max-h-28 overflow-y-auto whitespace-pre-wrap rounded-lg bg-white p-2 text-slate-800">
                  {formatValue(rev.new_value)}
                </pre>
              </div>
            </div>
            {rev.reason ? (
              <p className="mt-2 rounded-lg bg-white px-2 py-1 text-xs italic text-slate-500">
                依据：{rev.reason}
              </p>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-2">
              {isPendingRev ? (
                <>
                  <Button
                    size="sm"
                    onClick={() => apply.mutate(rev.id)}
                    disabled={apply.isPending}
                  >
                    {apply.isPending ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : null}
                    应用
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => reject.mutate(rev.id)}
                    disabled={reject.isPending}
                  >
                    驳回
                  </Button>
                </>
              ) : isAppliedRev ? (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    if (
                      !window.confirm(
                        `确认把「${fieldLabel[rev.field] ?? rev.field}」回滚到该版本？这会生成一条新的 user_edit 记录。`,
                      )
                    ) {
                      return;
                    }
                    rollback.mutate(rev.id);
                  }}
                  disabled={rollback.isPending}
                >
                  <UndoDot className="size-3.5" /> 回滚到此版本
                </Button>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}
