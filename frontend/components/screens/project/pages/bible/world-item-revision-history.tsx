"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, RotateCcw, X } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  type RevisionSource,
  type WorldItemRevision,
  worldItemRevisionsApi,
} from "@/lib/api";
import { ApiError } from "@/lib/http";
import { useScopedKey } from "@/lib/use-scoped-key";

const sourceLabel: Record<RevisionSource, string> = {
  user_edit: "用户编辑",
  copilot: "AI 共创",
  ai_inferred: "AI 推演",
};

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value.trim() || "—";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export type WorldItemRevisionHistoryProps = {
  projectId: string;
  itemId: string;
};

export function WorldItemRevisionHistory({
  projectId,
  itemId,
}: WorldItemRevisionHistoryProps) {
  const queryClient = useQueryClient();
  const key = useScopedKey("project", projectId, "world-item-revisions", itemId);
  const worldItemsKey = useScopedKey("project", projectId, "world-items");
  const pendingKey = useScopedKey("project", projectId, "world-item-pending");

  const { data: revisions = [], isPending } = useQuery({
    queryKey: key,
    queryFn: () => worldItemRevisionsApi.list(projectId, itemId),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: key });
    queryClient.invalidateQueries({ queryKey: worldItemsKey });
    queryClient.invalidateQueries({ queryKey: pendingKey });
  };

  const apply = useMutation({
    mutationFn: (revisionId: string) =>
      worldItemRevisionsApi.apply(projectId, itemId, revisionId),
    onSuccess: () => {
      toast.success("已应用");
      invalidate();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "应用失败"),
  });
  const reject = useMutation({
    mutationFn: (revisionId: string) =>
      worldItemRevisionsApi.reject(projectId, itemId, revisionId),
    onSuccess: () => {
      toast.success("已拒绝");
      invalidate();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "拒绝失败"),
  });
  const rollback = useMutation({
    mutationFn: (revisionId: string) =>
      worldItemRevisionsApi.rollback(projectId, itemId, revisionId),
    onSuccess: () => {
      toast.success("已回滚");
      invalidate();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "回滚失败"),
  });

  if (isPending) {
    return <p className="text-sm text-slate-500">正在读取历史…</p>;
  }
  if (revisions.length === 0) {
    return <p className="text-sm text-slate-500">暂无历史变更。</p>;
  }

  return (
    <ul className="space-y-3">
      {revisions.map((rev: WorldItemRevision) => (
        <li key={rev.id} className="rounded-xl border border-slate-200 bg-white p-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <Badge
              tone={
                rev.status === "applied"
                  ? "blue"
                  : rev.status === "pending"
                    ? "violet"
                    : "slate"
              }
            >
              {rev.status}
            </Badge>
            <span>{sourceLabel[rev.source] ?? rev.source}</span>
            <span>·</span>
            <span>字段：{rev.field}</span>
            {rev.scene_id ? (
              <>
                <span>·</span>
                <span className="truncate">scene: {rev.scene_id.slice(0, 12)}…</span>
              </>
            ) : null}
            {rev.created_at ? (
              <>
                <span>·</span>
                <span>{new Date(rev.created_at).toLocaleString()}</span>
              </>
            ) : null}
          </div>
          <div className="mt-2 space-y-1 text-sm">
            <p className="text-slate-500">
              旧值：<span className="text-slate-800">{formatValue(rev.old_value)}</span>
            </p>
            <p className="text-slate-500">
              新值：<span className="text-slate-950 font-semibold">{formatValue(rev.new_value)}</span>
            </p>
            {rev.reason ? (
              <p className="text-xs text-slate-500">理由：{rev.reason}</p>
            ) : null}
          </div>
          <div className="mt-3 flex gap-2">
            {rev.status === "pending" ? (
              <>
                <Button
                  size="sm"
                  onClick={() => apply.mutate(rev.id)}
                  disabled={apply.isPending}
                >
                  <Check className="size-3.5" /> 应用
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => reject.mutate(rev.id)}
                  disabled={reject.isPending}
                >
                  <X className="size-3.5" /> 拒绝
                </Button>
              </>
            ) : null}
            {rev.status === "superseded" || rev.status === "applied" ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => rollback.mutate(rev.id)}
                disabled={rollback.isPending}
              >
                <RotateCcw className="size-3.5" /> 回滚到此版本
              </Button>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  );
}
