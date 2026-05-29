"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import {
  type ChapterStateRequirement,
  type StoryStateHistory,
  type StoryStateItem,
  type StoryStatePatch,
  type StoryStateStatus,
  storyStatesApi,
} from "@/lib/api";
import { ApiError } from "@/lib/http";
import { useScopedKey } from "@/lib/use-scoped-key";

const stateTypeLabel: Record<string, string> = {
  skill: "能力",
  artifact: "器物",
  identity: "身份",
  grudge: "恩怨",
  foreshadow: "伏笔",
  oath: "誓约",
};

const entityTypeLabel: Record<string, string> = {
  character: "人物",
  artifact: "器物",
  plot_thread: "剧情线",
  relationship: "关系",
  world_rule: "世界规则",
};

const statusOptions: StoryStateStatus[] = [
  "active",
  "hidden",
  "damaged",
  "resolved",
  "consumed",
  "inactive",
];

type DetailTab = "detail" | "history" | "edit";

type StoryStateDetailDialogProps = {
  projectId: string;
  state: StoryStateItem;
  onClose: () => void;
  onSaved: () => void;
};

type StoryStateListDialogProps = {
  items: StoryStateItem[];
  onClose: () => void;
  onSelectState: (state: StoryStateItem) => void;
};

type ChapterRequirementListDialogProps = {
  chapterLabel: string;
  items: Array<{ requirement: ChapterStateRequirement; state: StoryStateItem | null }>;
  onClose: () => void;
  onSelectState: (state: StoryStateItem) => void;
};

const requirementTypeLabel: Record<string, string> = {
  must_remember: "必须承接",
  must_not_conflict: "禁止冲突",
  should_reference: "建议呼应",
  candidate_payoff: "可回收",
};

function requirementTone(type: string) {
  if (type === "must_not_conflict") return "rose" as const;
  if (type === "must_remember") return "amber" as const;
  if (type === "candidate_payoff") return "violet" as const;
  return "blue" as const;
}

function formatJson(value: unknown) {
  if (!value || (typeof value === "object" && Object.keys(value).length === 0)) {
    return "{}";
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "{}";
  }
}

function formatHistoryValue(value: unknown): string {
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

function changedFields(before: StoryStateHistory["before_json"], after: StoryStateHistory["after_json"]) {
  const keys = new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]);
  return Array.from(keys).filter((key) => {
    try {
      return JSON.stringify(before?.[key]) !== JSON.stringify(after?.[key]);
    } catch {
      return before?.[key] !== after?.[key];
    }
  });
}

export function StoryStateDetailDialog({
  projectId,
  state,
  onClose,
  onSaved,
}: StoryStateDetailDialogProps) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<DetailTab>("detail");
  const detailKey = useScopedKey("project", projectId, "story-state", state.id);
  const historyKey = useScopedKey("project", projectId, "story-state", state.id, "history");

  const { data: detail = state } = useQuery({
    queryKey: detailKey,
    queryFn: () => storyStatesApi.get(projectId, state.id),
    initialData: state,
  });
  const { data: historyResponse, isPending: isHistoryPending } = useQuery({
    queryKey: historyKey,
    queryFn: () => storyStatesApi.history(projectId, state.id),
  });
  const history = useMemo(
    () => historyResponse?.items ?? [],
    [historyResponse],
  );

  const [summary, setSummary] = useState(detail.summary);
  const [status, setStatus] = useState<StoryStateStatus>(detail.status);
  const [priority, setPriority] = useState(String(detail.priority));
  const [isHardConstraint, setIsHardConstraint] = useState(detail.is_hard_constraint);
  const [valueJson, setValueJson] = useState(formatJson(detail.value_json));
  const [reason, setReason] = useState("人工修正关键设定");

  useEffect(() => {
    setSummary(detail.summary);
    setStatus(detail.status);
    setPriority(String(detail.priority));
    setIsHardConstraint(detail.is_hard_constraint);
    setValueJson(formatJson(detail.value_json));
  }, [detail]);

  const save = useMutation({
    mutationFn: () => {
      let parsedValue: Record<string, unknown>;
      try {
        const parsed = JSON.parse(valueJson || "{}");
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          throw new Error("value_json_must_be_object");
        }
        parsedValue = parsed as Record<string, unknown>;
      } catch {
        toast.error("扩展字段必须是合法 JSON 对象");
        return Promise.reject(new Error("invalid_value_json"));
      }

      const parsedPriority = Number(priority);
      if (!Number.isInteger(parsedPriority) || parsedPriority < 0) {
        toast.error("优先级必须是非负整数");
        return Promise.reject(new Error("invalid_priority"));
      }

      const payload: StoryStatePatch = {
        status,
        summary,
        priority: parsedPriority,
        is_hard_constraint: isHardConstraint,
        value_json: parsedValue,
        reason: reason.trim() || "人工修正关键设定",
      };
      return storyStatesApi.update(projectId, detail.id, payload);
    },
    onSuccess: () => {
      toast.success("关键设定已更新");
      queryClient.invalidateQueries({ queryKey: detailKey });
      queryClient.invalidateQueries({ queryKey: historyKey });
      onSaved();
      setTab("detail");
    },
    onError: (error: unknown) => {
      if (error instanceof Error && error.message.startsWith("invalid_")) return;
      toast.error(error instanceof ApiError ? error.message : "保存失败");
    },
  });

  return (
    <Modal title={detail.name || "关键设定详情"} onClose={onClose}>
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="blue">{stateTypeLabel[detail.state_type] ?? detail.state_type}</Badge>
          <Badge tone="slate">{entityTypeLabel[detail.entity_type] ?? detail.entity_type}</Badge>
          <Badge tone={detail.status === "active" ? "green" : "amber"}>{detail.status}</Badge>
          {detail.is_hard_constraint ? <Badge tone="rose">硬约束</Badge> : null}
          <Badge tone="slate">P{detail.priority}</Badge>
        </div>

        <div className="flex gap-2 border-b border-slate-200 text-sm">
          {[
            { key: "detail" as const, label: "详情" },
            { key: "history" as const, label: "历史" },
            { key: "edit" as const, label: "修正" },
          ].map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setTab(item.key)}
              className={`-mb-px border-b-2 px-3 py-2 font-semibold transition ${
                tab === item.key
                  ? "border-slate-950 text-slate-950"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        {tab === "detail" ? (
          <div className="space-y-4">
            <section className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-400">
                摘要
              </p>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">
                {detail.summary || "—"}
              </p>
            </section>
            <div className="grid gap-3 md:grid-cols-2">
              <InfoRow label="来源章节" value={detail.source_chapter_id ?? "—"} />
              <InfoRow label="来源场景" value={detail.source_scene_id ?? "—"} />
              <InfoRow label="最近更新章节" value={detail.updated_in_chapter_id ?? "—"} />
              <InfoRow label="实体 ID" value={detail.entity_id ?? "—"} />
            </div>
            {detail.source_excerpt ? (
              <section className="rounded-2xl border border-slate-200 bg-white p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-400">
                  来源片段
                </p>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">
                  {detail.source_excerpt}
                </p>
              </section>
            ) : null}
            <section className="rounded-2xl border border-slate-200 bg-slate-950 p-4 text-slate-100">
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-400">
                扩展字段
              </p>
              <pre className="mt-2 max-h-52 overflow-auto whitespace-pre-wrap text-xs leading-5">
                {formatJson(detail.value_json)}
              </pre>
            </section>
          </div>
        ) : null}

        {tab === "history" ? (
          <div className="max-h-[60vh] overflow-y-auto">
            {isHistoryPending ? (
              <p className="text-sm text-slate-500">正在读取历史…</p>
            ) : history.length === 0 ? (
              <p className="text-sm text-slate-500">暂无历史变更。</p>
            ) : (
              <ul className="space-y-3">
                {history.map((item) => {
                  const fields = changedFields(item.before_json, item.after_json);
                  return (
                    <li key={item.id} className="rounded-xl border border-slate-200 bg-white p-3">
                      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                        <Badge tone="violet">{item.change_type}</Badge>
                        {item.created_at ? <span>{new Date(item.created_at).toLocaleString()}</span> : null}
                        {item.chapter_id ? <span>章节：{item.chapter_id.slice(0, 12)}…</span> : null}
                        {item.scene_id ? <span>场景：{item.scene_id.slice(0, 12)}…</span> : null}
                      </div>
                      {item.reason ? (
                        <p className="mt-2 text-sm font-semibold text-slate-800">
                          {item.reason}
                        </p>
                      ) : null}
                      {fields.length > 0 ? (
                        <div className="mt-2 space-y-1 text-xs text-slate-500">
                          {fields.slice(0, 6).map((field) => (
                            <p key={field}>
                              {field}：{formatHistoryValue(item.before_json?.[field])} →{" "}
                              <span className="font-semibold text-slate-900">
                                {formatHistoryValue(item.after_json?.[field])}
                              </span>
                            </p>
                          ))}
                        </div>
                      ) : null}
                      {item.source_excerpt ? (
                        <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-500">
                          {item.source_excerpt}
                        </p>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        ) : null}

        {tab === "edit" ? (
          <div className="space-y-3">
            <label className="block text-sm font-semibold text-slate-700">
              摘要
              <textarea
                rows={4}
                value={summary}
                onChange={(event) => setSummary(event.target.value)}
                className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm leading-6 outline-none focus:border-indigo-500"
              />
            </label>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="block text-sm font-semibold text-slate-700">
                状态
                <select
                  value={status}
                  onChange={(event) => setStatus(event.target.value as StoryStateStatus)}
                  className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-indigo-500"
                >
                  {statusOptions.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm font-semibold text-slate-700">
                优先级
                <input
                  type="number"
                  min={0}
                  value={priority}
                  onChange={(event) => setPriority(event.target.value)}
                  className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-indigo-500"
                />
              </label>
            </div>
            <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
              <input
                type="checkbox"
                checked={isHardConstraint}
                onChange={(event) => setIsHardConstraint(event.target.checked)}
              />
              硬约束
            </label>
            <label className="block text-sm font-semibold text-slate-700">
              扩展字段 JSON
              <textarea
                rows={6}
                value={valueJson}
                onChange={(event) => setValueJson(event.target.value)}
                className="mt-1 w-full rounded-xl border border-slate-200 bg-slate-950 px-3 py-2 font-mono text-xs leading-5 text-slate-100 outline-none focus:border-indigo-500"
              />
            </label>
            <label className="block text-sm font-semibold text-slate-700">
              修正原因
              <input
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-indigo-500"
              />
            </label>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="ghost" onClick={() => setTab("detail")}>
                取消
              </Button>
              <Button
                onClick={() => save.mutate()}
                disabled={save.isPending || !summary.trim()}
              >
                <Save className="size-4" />
                {save.isPending ? "保存中…" : "保存修正"}
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </Modal>
  );
}

export function StoryStateListDialog({
  items,
  onClose,
  onSelectState,
}: StoryStateListDialogProps) {
  return (
    <Modal title="关键设定" onClose={onClose}>
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <div>
            <p className="text-sm font-black text-slate-950">当前活跃状态项</p>
            <p className="mt-0.5 text-xs text-slate-500">共 {items.length} 条。</p>
          </div>
          <Badge tone={items.length > 0 ? "blue" : "slate"}>{items.length} 条</Badge>
        </div>
        {items.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-white px-4 py-10 text-center">
            <p className="text-sm font-semibold text-slate-700">暂无关键设定</p>
            <p className="mt-1 text-xs text-slate-500">
              完成或重写正文后，系统会从正文里提取人物状态、伏笔、能力、器物等记录。
            </p>
          </div>
        ) : (
          <div className="max-h-[60vh] divide-y divide-slate-100 overflow-y-auto rounded-2xl border border-slate-200 bg-white">
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelectState(item)}
                className="block w-full px-4 py-3 text-left transition hover:bg-slate-50"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="blue">{stateTypeLabel[item.state_type] ?? item.state_type}</Badge>
                      <Badge tone="slate">
                        {entityTypeLabel[item.entity_type] ?? item.entity_type}
                      </Badge>
                      {item.is_hard_constraint ? <Badge tone="rose">硬约束</Badge> : null}
                    </div>
                    <p className="mt-2 truncate text-sm font-bold text-slate-950">
                      {item.name}
                    </p>
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">
                      {item.summary || "—"}
                    </p>
                  </div>
                  <span className="shrink-0 text-[11px] font-semibold text-slate-400">
                    P{item.priority}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </Modal>
  );
}

export function ChapterRequirementListDialog({
  chapterLabel,
  items,
  onClose,
  onSelectState,
}: ChapterRequirementListDialogProps) {
  return (
    <Modal title="本章承接要求" onClose={onClose}>
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <div>
            <p className="text-sm font-black text-slate-950">{chapterLabel}</p>
            <p className="mt-0.5 text-xs text-slate-500">当前章节需要保持一致的状态项。</p>
          </div>
          <Badge tone={items.length > 0 ? "amber" : "slate"}>{items.length} 条</Badge>
        </div>
        {items.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-white px-4 py-10 text-center">
            <p className="text-sm font-semibold text-slate-700">本章暂无承接要求</p>
            <p className="mt-1 text-xs text-slate-500">
              后续生成场景或写正文时，系统会把需要承接的关键设定写入这里。
            </p>
          </div>
        ) : (
          <div className="max-h-[60vh] divide-y divide-slate-100 overflow-y-auto rounded-2xl border border-slate-200 bg-white">
            {items.map(({ requirement, state }) => {
              const content = (
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={requirementTone(requirement.requirement_type)}>
                        {requirementTypeLabel[requirement.requirement_type] ??
                          requirement.requirement_type}
                      </Badge>
                      {state?.is_hard_constraint ? <Badge tone="rose">硬约束</Badge> : null}
                    </div>
                    <p className="mt-2 truncate text-sm font-bold text-slate-950">
                      {state?.name ?? "未匹配到关键设定"}
                    </p>
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">
                      {requirement.summary || state?.summary || "—"}
                    </p>
                    <p className="mt-1 truncate text-[11px] text-slate-400">
                      {state
                        ? `${entityTypeLabel[state.entity_type] ?? state.entity_type} · ${
                            stateTypeLabel[state.state_type] ?? state.state_type
                          }`
                        : `关联 ID：${requirement.state_item_id}`}
                    </p>
                  </div>
                  <span className="shrink-0 text-[11px] font-semibold text-slate-400">
                    P{requirement.priority}
                  </span>
                </div>
              );

              return state ? (
                <button
                  key={requirement.id}
                  type="button"
                  onClick={() => onSelectState(state)}
                  className="block w-full px-4 py-3 text-left transition hover:bg-slate-50"
                >
                  {content}
                </button>
              ) : (
                <div key={requirement.id} className="px-4 py-3">
                  {content}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </Modal>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-3">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
        {label}
      </p>
      <p className="mt-1 truncate text-sm font-semibold text-slate-800">{value}</p>
    </div>
  );
}
