"use client";

/**
 * BatchJobProgressDialog：批量任务进度通用弹窗。
 *
 * 设计要点：
 * - SSE 优先：订阅 ``project:{projectId}`` 推流，过滤 ``batch_job.*`` 事件实时更新计数。
 * - 轮询兜底：每 4s 调 ``batchApi.getProgress`` 一次，避免 SSE 漏推或刚打开未连上时无进度。
 *   完成 / 失败后停止轮询。
 * - 终态触发 onComplete：``status === "succeeded" | "failed" | "cancelled"`` 调 onComplete(progress)，
 *   外部页面负责 invalidate / refetch + 关闭弹窗。
 * - 仅展示，无业务副作用：组件本身不写库、不触发额外 mutation。
 *
 * 复用 useProjectEvents（lib/hooks/use-event-source.ts）做断线重连。
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { batchApi, type BatchJobProgress } from "@/lib/api";
import { useProjectEvents } from "@/lib/hooks/use-event-source";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { ProgressBar } from "@/components/ui/progress";

const POLL_INTERVAL_MS = 4000;

const BATCH_TYPE_LABEL: Record<string, string> = {
  scene_plan: "批量场景规划",
  scene_write: "批量场景写作",
  audit: "批量审稿",
  rewrite: "批量重写",
  polish: "批量章后润色",
};

const STATUS_LABEL: Record<string, string> = {
  queued: "排队中",
  running: "运行中",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const STATUS_TONE: Record<string, "indigo" | "green" | "orange" | "rose"> = {
  queued: "indigo",
  running: "indigo",
  succeeded: "green",
  failed: "rose",
  cancelled: "orange",
};

function isTerminalStatus(status: string | undefined): boolean {
  return status === "succeeded" || status === "failed" || status === "cancelled";
}

export type BatchJobProgressDialogProps = {
  projectId: string;
  batchJobId: string;
  title?: string;
  /** 终态（succeeded / failed / cancelled）时回调一次。 */
  onComplete?: (progress: BatchJobProgress) => void;
  onClose: () => void;
};

type ProgressState = {
  status: string;
  batchType: string;
  total: number;
  completed: number;
  failed: number;
  runningTargets: string[];
  finishedAt?: string | null;
};

const INITIAL_STATE: ProgressState = {
  status: "queued",
  batchType: "",
  total: 0,
  completed: 0,
  failed: 0,
  runningTargets: [],
  finishedAt: null,
};

export function BatchJobProgressDialog({
  projectId,
  batchJobId,
  title,
  onComplete,
  onClose,
}: BatchJobProgressDialogProps) {
  const [state, setState] = useState<ProgressState>(INITIAL_STATE);
  const [completed, setCompleted] = useState(false);

  const applyProgress = useCallback((p: BatchJobProgress) => {
    const out = p.output_payload ?? {};
    setState((prev) => ({
      status: p.status ?? prev.status,
      batchType: (out.batch_type as string) ?? prev.batchType,
      total: out.total_items ?? prev.total,
      completed: out.completed_items ?? prev.completed,
      failed: out.failed_items ?? prev.failed,
      runningTargets: (out.running_target_ids as string[] | undefined) ?? prev.runningTargets,
      finishedAt: out.finished_at ?? prev.finishedAt ?? null,
    }));
    if (isTerminalStatus(p.status) && !completed) {
      setCompleted(true);
      onComplete?.(p);
    }
  }, [completed, onComplete]);

  // 轮询兜底
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      try {
        const data = await batchApi.getProgress(projectId, batchJobId);
        if (cancelled) return;
        applyProgress(data);
        if (!isTerminalStatus(data.status)) {
          timer = setTimeout(tick, POLL_INTERVAL_MS);
        }
      } catch {
        if (!cancelled) {
          timer = setTimeout(tick, POLL_INTERVAL_MS);
        }
      }
    };

    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [projectId, batchJobId, applyProgress]);

  // SSE 增量更新（同一 batch_job_id 的事件）
  useProjectEvents(projectId, {
    filter: [
      "batch_job.started",
      "batch_job.item_started",
      "batch_job.item_succeeded",
      "batch_job.item_failed",
      "batch_job.completed",
      "batch_job.failed",
    ],
    onMessage: (event) => {
      const payload = event.payload ?? {};
      if (payload.batch_job_id !== batchJobId) return;

      const batchType = (payload.batch_type as string | undefined) ?? "";
      const totalItems = payload.total_items as number | undefined;
      const completedItems = payload.completed_items as number | undefined;
      const failedItems = payload.failed_items as number | undefined;
      const targetId = payload.target_id as string | undefined;

      if (event.type === "batch_job.started") {
        setState((prev) => ({
          ...prev,
          status: "running",
          batchType: batchType || prev.batchType,
          total: totalItems ?? prev.total,
        }));
        return;
      }
      if (event.type === "batch_job.item_started" && targetId) {
        setState((prev) => ({
          ...prev,
          status: "running",
          runningTargets: prev.runningTargets.includes(targetId)
            ? prev.runningTargets
            : [...prev.runningTargets, targetId],
        }));
        return;
      }
      if (event.type === "batch_job.item_succeeded" || event.type === "batch_job.item_failed") {
        setState((prev) => ({
          ...prev,
          completed: completedItems ?? prev.completed,
          failed: failedItems ?? prev.failed,
          runningTargets: targetId
            ? prev.runningTargets.filter((id) => id !== targetId)
            : prev.runningTargets,
        }));
        return;
      }
      if (event.type === "batch_job.completed" || event.type === "batch_job.failed") {
        // 终态以轮询返回的完整 progress 为准（onComplete 在轮询中触发）。
        setState((prev) => ({
          ...prev,
          status: event.type === "batch_job.completed" ? "succeeded" : "failed",
          completed: completedItems ?? prev.completed,
          failed: failedItems ?? prev.failed,
          runningTargets: [],
        }));
      }
    },
  });

  const total = state.total || 0;
  const done = state.completed + state.failed;
  const percent = total > 0 ? (done / total) * 100 : 0;
  const queued = Math.max(total - done - state.runningTargets.length, 0);

  const heading = useMemo(() => {
    if (title) return title;
    const label = BATCH_TYPE_LABEL[state.batchType] || "批量任务";
    return `${label}进度`;
  }, [title, state.batchType]);

  const statusLabel = STATUS_LABEL[state.status] ?? state.status;
  const tone = STATUS_TONE[state.status] ?? "indigo";

  return (
    <Modal title={heading} onClose={onClose}>
      <div className="space-y-5">
        <div className="flex items-center justify-between text-sm">
          <div className="text-slate-600">
            状态：<span className="font-semibold text-slate-900">{statusLabel}</span>
          </div>
          <div className="text-slate-500">
            {done} / {total}（{Math.round(percent)}%）
          </div>
        </div>

        <ProgressBar value={percent} tone={tone} />

        <div className="grid grid-cols-4 gap-3 text-center text-xs">
          <Cell label="排队" value={queued} tone="indigo" />
          <Cell label="运行" value={state.runningTargets.length} tone="indigo" />
          <Cell label="成功" value={state.completed} tone="green" />
          <Cell label="失败" value={state.failed} tone="rose" />
        </div>

        {state.runningTargets.length > 0 && (
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
            <div className="mb-2 text-xs font-semibold text-slate-700">
              正在处理 {state.runningTargets.length} 项
            </div>
            <ul className="space-y-1 text-xs text-slate-600">
              {state.runningTargets.slice(0, 10).map((id) => (
                <li key={id} className="truncate font-mono">{id}</li>
              ))}
              {state.runningTargets.length > 10 && (
                <li className="text-slate-400">…还有 {state.runningTargets.length - 10} 项</li>
              )}
            </ul>
          </div>
        )}

        <div className="flex items-center justify-end gap-2 pt-2">
          {isTerminalStatus(state.status) ? (
            <Button onClick={onClose}>关闭</Button>
          ) : (
            <Button variant="secondary" onClick={onClose}>
              后台运行
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}

function Cell({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "indigo" | "green" | "orange" | "rose";
}) {
  const color = {
    indigo: "text-indigo-700 bg-indigo-50",
    green: "text-emerald-700 bg-emerald-50",
    orange: "text-orange-700 bg-orange-50",
    rose: "text-rose-700 bg-rose-50",
  }[tone];
  return (
    <div className={`rounded-xl px-2 py-3 ${color}`}>
      <div className="text-lg font-black">{value}</div>
      <div className="mt-1 text-[11px] font-medium opacity-80">{label}</div>
    </div>
  );
}
