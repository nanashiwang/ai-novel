"use client";

import { useMutation } from "@tanstack/react-query";
import { AlertCircle, Bot, CheckCircle2, Loader2, RefreshCw, Send, Sparkles, UserRound, X } from "lucide-react";
import { type FormEvent, useCallback, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import {
  type GenerationJob,
  type RevisionMessage,
  type RevisionMode,
  type RevisionProposal,
  type RevisionTargetType,
  revisionApi,
} from "@/lib/api";
import { ApiError } from "@/lib/http";
import { useProjectEvents, type ProjectEvent } from "@/lib/hooks/use-event-source";

const targetLabel: Record<string, string> = {
  project_settings: "项目设置",
  story_bible: "核心设定",
  character: "人物",
  world_item: "世界观",
  plot_thread: "剧情线",
  chapter: "章节大纲",
  story_bible_bundle: "完整圣经快照",
};

function formatValue(value: unknown): string {
  if (Array.isArray(value)) return value.join("、");
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value ?? "");
}

function proposalScopeLabel(proposal: RevisionProposal) {
  return `${targetLabel[proposal.target_type] ?? proposal.target_type}${
    proposal.action === "create" ? " · 新增" : " · 更新"
  }`;
}

type ProposalGroup = {
  key: string;
  groupId: string | null;
  title: string;
  proposals: RevisionProposal[];
  primary: RevisionProposal[];
  linked: RevisionProposal[];
  riskNotes: string[];
  applied: boolean;
};

function BiblePreviewItem({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <p className="text-xs font-black text-slate-400">{label}</p>
      <p className="line-clamp-4 break-words text-slate-800">{formatValue(value) || "—"}</p>
    </div>
  );
}

export type RevisionCopilotDrawerProps = {
  projectId: string;
  scope: string;
  targetType?: RevisionTargetType | null;
  targetId?: string | null;
  title: string;
  description?: string;
  starterPrompts: string[];
  defaultMode?: RevisionMode;
  onClose: () => void;
  onApplied: () => void;
};

export function RevisionCopilotDrawer({
  projectId,
  scope,
  targetType = null,
  targetId = null,
  title,
  description,
  starterPrompts,
  defaultMode = "patch",
  onClose,
  onApplied,
}: RevisionCopilotDrawerProps) {
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<RevisionMessage[]>([]);
  const [proposals, setProposals] = useState<RevisionProposal[]>([]);
  const [applyingKey, setApplyingKey] = useState<string | null>(null);
  const [mode, setMode] = useState<RevisionMode>(defaultMode);
  const [lastUserMessage, setLastUserMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [backgroundJob, setBackgroundJob] = useState<GenerationJob | null>(null);
  const [backgroundStatus, setBackgroundStatus] = useState<"idle" | "queued" | "running" | "succeeded" | "failed">(
    "idle",
  );
  const [backgroundError, setBackgroundError] = useState("");

  const refreshSession = useCallback(
    async (currentSessionId: string) => {
      const data = await revisionApi.getSession(projectId, currentSessionId);
      setSessionId(data.session.id);
      setMessages(data.messages);
      setProposals(data.proposals);
      return data;
    },
    [projectId],
  );

  const handleProjectEvent = useCallback(
    (event: ProjectEvent) => {
      if (!backgroundJob || !event.type.startsWith("job.")) return;
      if (event.payload.job_id !== backgroundJob.id) return;
      const status = String(event.payload.status || "");
      if (status === "running") {
        setBackgroundStatus("running");
        return;
      }
      if (event.type === "job.succeeded") {
        setBackgroundStatus("succeeded");
        const targetSessionId =
          typeof backgroundJob.input_payload?.revision_session_id === "string"
            ? backgroundJob.input_payload.revision_session_id
            : sessionId;
        if (targetSessionId) {
          void refreshSession(targetSessionId).catch(() => {
            setBackgroundError("后台任务已完成，但刷新提案失败。");
          });
        }
        onApplied();
      } else if (event.type === "job.failed") {
        setBackgroundStatus("failed");
        setBackgroundError(String(event.payload.error_message || backgroundJob.error_message || "后台生成失败"));
      }
    },
    [backgroundJob, onApplied, refreshSession, sessionId],
  );
  useProjectEvents(projectId, {
    onMessage: handleProjectEvent,
    enabled: Boolean(backgroundJob) && ["queued", "running"].includes(backgroundStatus),
  });

  const chat = useMutation({
    mutationFn: ({
      message,
      currentSessionId,
      requestMode,
    }: {
      message: string;
      currentSessionId: string | null;
      requestMode: RevisionMode;
    }) =>
      revisionApi.chat(projectId, {
        message,
        session_id: currentSessionId,
        scope,
        target_type: targetType,
        target_id: targetId,
        mode: requestMode,
      }),
    onSuccess: (data) => {
      setErrorMessage("");
      setSessionId(data.session.id);
      setMessages(data.messages);
      setProposals(data.proposals);
      if (data.job) {
        setBackgroundJob(data.job);
        setBackgroundStatus(data.job.status === "running" ? "running" : "queued");
        setBackgroundError("");
        toast.success("已提交后台任务生成完整故事圣经快照");
        return;
      }
      setBackgroundJob(null);
      setBackgroundStatus("idle");
      setBackgroundError("");
      if (data.proposals.length === 0) {
        toast.warning("AI 只返回了建议，未生成可应用修改");
      }
    },
    onError: (e: unknown) => {
      const message = e instanceof ApiError ? e.message : "AI 优化失败";
      setErrorMessage(message);
      toast.error(message);
    },
  });

  const submitMessage = useCallback(
    (rawMessage: string, modeOverride?: RevisionMode) => {
      const message = rawMessage.trim();
      if (!message || chat.isPending) return;
      const requestMode = modeOverride ?? mode;
      setInput("");
      setErrorMessage("");
      setBackgroundError("");
      setLastUserMessage(message);
      setProposals([]);
      if (requestMode !== "full_project_rewrite") {
        setBackgroundJob(null);
        setBackgroundStatus("idle");
      }
      setMessages((prev) => [
        ...prev,
        {
          id: `optimistic-${Date.now()}`,
          session_id: sessionId ?? "",
          role: "user",
          content: message,
        },
      ]);
      chat.mutate({ message, currentSessionId: sessionId, requestMode });
    },
    [chat, mode, sessionId],
  );

  const groups = useMemo<ProposalGroup[]>(() => {
    const map = new Map<string, RevisionProposal[]>();
    for (const proposal of proposals) {
      const key = proposal.group_id || proposal.id;
      map.set(key, [...(map.get(key) ?? []), proposal]);
    }
    return Array.from(map.entries()).map(([key, rows]) => {
      const groupId = rows[0]?.group_id ?? null;
      const primary = rows.filter(
        (item) => item.is_primary || (!!targetType && item.target_type === targetType),
      );
      const safePrimary = primary.length > 0 ? primary : rows.slice(0, 1);
      const primaryIds = new Set(safePrimary.map((item) => item.id));
      const linked = rows.filter((item) => !primaryIds.has(item.id));
      const riskNotes = Array.from(new Set(rows.flatMap((item) => item.risk_notes ?? []))).filter(Boolean);
      return {
        key,
        groupId,
        title: rows[0]?.group_title || rows[0]?.title || "设定优化提案",
        proposals: rows,
        primary: safePrimary,
        linked,
        riskNotes,
        applied: rows.every((item) => item.status === "applied"),
      };
    });
  }, [proposals, targetType]);

  const apply = useMutation({
    mutationFn: (proposalId: string) => revisionApi.applyProposal(projectId, proposalId),
    onMutate: (proposalId) => setApplyingKey(proposalId),
    onSuccess: (data) => {
      setProposals((prev) =>
        prev.map((item) => (item.id === data.proposal.id ? data.proposal : item)),
      );
      onApplied();
      toast.success("提案已应用");
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "应用失败"),
    onSettled: () => setApplyingKey(null),
  });

  const applyGroup = useMutation({
    mutationFn: (groupId: string) => revisionApi.applyProposalGroup(projectId, groupId),
    onMutate: (groupId) => setApplyingKey(groupId),
    onSuccess: (data) => {
      const updated = new Map(data.proposals.map((item) => [item.id, item]));
      setProposals((prev) => prev.map((item) => updated.get(item.id) ?? item));
      onApplied();
      toast.success("整组提案已应用");
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "应用失败"),
    onSettled: () => setApplyingKey(null),
  });

  const applyWithRebuild = useMutation({
    mutationFn: (proposalId: string) =>
      revisionApi.applyProposalWithRebuild(projectId, proposalId, {
        estimate_words: 20_000,
        target_chapters: null,
        scenes_per_chapter: 3,
        write_drafts: true,
      }),
    onMutate: (proposalId) => setApplyingKey(`rebuild:${proposalId}`),
    onSuccess: (data) => {
      setProposals((prev) =>
        prev.map((item) => (item.id === data.proposal.id ? data.proposal : item)),
      );
      onApplied();
      toast.success("已应用设定并提交全项目重构任务");
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "应用并重构失败"),
    onSettled: () => setApplyingKey(null),
  });

  const send = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    submitMessage(input);
  };

  const renderBundlePreview = (proposal: RevisionProposal) => {
    const bible = proposal.patch.story_bible as Record<string, unknown> | undefined;
    if (!bible || typeof bible !== "object") return null;
    const characters = Array.isArray(bible.main_characters) ? bible.main_characters : [];
    const locations = Array.isArray(bible.locations) ? bible.locations : [];
    const factions = Array.isArray(bible.factions) ? bible.factions : [];
    const worldRules = Array.isArray(bible.world_rules) ? bible.world_rules : [];
    const plotThreads = Array.isArray(bible.plot_threads) ? bible.plot_threads : [];
    const impactCounts = proposal.patch.impact_counts as
      | { current?: Record<string, unknown>; new?: Record<string, unknown> }
      | undefined;
    const currentCounts = impactCounts?.current ?? {};
    const names = characters
      .map((item) =>
        item && typeof item === "object" && "name" in item
          ? String((item as { name?: unknown }).name ?? "")
          : "",
      )
      .filter(Boolean);
    return (
      <div className="mt-3 space-y-3 rounded-2xl bg-slate-50 p-3">
        <div className="grid gap-2 text-sm md:grid-cols-2">
          <BiblePreviewItem label="Premise" value={bible.premise} />
          <BiblePreviewItem label="Theme" value={bible.theme} />
          <BiblePreviewItem label="Genre" value={bible.genre} />
          <BiblePreviewItem label="Tone" value={bible.tone} />
          <BiblePreviewItem label="POV" value={bible.narrative_pov} />
          <BiblePreviewItem label="Style" value={bible.style_guide} />
        </div>
        <p className="text-xs text-slate-500">
          新快照：人物 {characters.length} 个{names.length ? `（${names.slice(0, 6).join("、")}）` : ""}；
          地点 {locations.length}；势力 {factions.length}；世界规则 {worldRules.length}；剧情线 {plotThreads.length}。
        </p>
        <p className="text-xs text-slate-500">
          当前下游：大纲 {formatValue(currentCounts.chapters) || 0} 章；世界观{" "}
          {formatValue(currentCounts.world_items) || 0} 条；剧情线{" "}
          {formatValue(currentCounts.plot_threads) || 0} 条。预计重构额度：20,000 字。
        </p>
        <p className="text-xs text-amber-700">
          “应用并重构项目”会清理旧大纲、场景、正文、审稿问题和场景记忆，然后提交 full_novel 任务。
        </p>
      </div>
    );
  };

  const renderProposalList = (label: string, rows: RevisionProposal[]) => {
    if (rows.length === 0) return null;
    return (
      <div className="mt-3 rounded-2xl bg-slate-50 p-3">
        <p className="mb-2 text-xs font-black text-slate-500">{label}</p>
        <div className="space-y-3">
          {rows.map((proposal) => (
            <div key={proposal.id} className="rounded-2xl bg-white p-3 ring-1 ring-slate-200">
              <div className="mb-2 flex flex-wrap gap-2">
                <Badge tone={proposal.status === "applied" ? "green" : "amber"}>
                  {proposal.status === "applied" ? "已应用" : "待确认"}
                </Badge>
                <Badge tone="blue">{proposalScopeLabel(proposal)}</Badge>
              </div>
              <h4 className="font-black text-slate-950">{proposal.title}</h4>
              {proposal.reason ? <p className="mt-1 text-sm text-slate-500">{proposal.reason}</p> : null}
              {proposal.target_type === "story_bible_bundle" ? (
                renderBundlePreview(proposal)
              ) : (
                <div className="mt-2 space-y-1">
                  {Object.entries(proposal.patch).map(([key, value]) => (
                    <div key={key} className="grid gap-1 text-sm md:grid-cols-[120px_1fr]">
                      <span className="font-bold text-slate-500">{key}</span>
                      <span className="break-words text-slate-800">{formatValue(value)}</span>
                    </div>
                  ))}
                </div>
              )}
              {proposal.impact.length > 0 ? (
                <p className="mt-2 text-xs text-slate-400">影响范围：{proposal.impact.join("、")}</p>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/35" onClick={onClose}>
      <aside
        className="ml-auto flex h-full w-full max-w-2xl flex-col overflow-hidden bg-white shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="border-b border-slate-200 bg-slate-950 px-6 py-5 text-white">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-bold text-cyan-100">
                <Sparkles className="size-3.5" /> AI 模块优化
              </div>
              <h2 className="mt-3 text-xl font-black">{title}</h2>
              <p className="mt-1 text-sm text-slate-300">
                {description || "AI 只生成修改提案；点击应用后才会写入项目。"}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl p-2 text-slate-300 hover:bg-white/10 hover:text-white"
              aria-label="关闭"
            >
              <X className="size-5" />
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto bg-slate-50 p-5">
          {messages.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-6">
              <p className="font-black text-slate-950">先选择优化模式，再输入目标或点一个示例：</p>
              <div className="mt-3 grid gap-2 rounded-2xl bg-slate-50 p-2 text-sm md:grid-cols-2">
                <button
                  type="button"
                  onClick={() => setMode("patch")}
                  className={cn(
                    "rounded-xl px-4 py-3 text-left",
                    mode === "patch" ? "bg-white shadow-sm ring-1 ring-cyan-200" : "hover:bg-white",
                  )}
                >
                  <span className="font-black text-slate-950">局部优化</span>
                  <span className="mt-1 block text-xs text-slate-500">生成小 patch，适合微调单个模块。</span>
                </button>
                <button
                  type="button"
                  onClick={() => setMode("full_project_rewrite")}
                  className={cn(
                    "rounded-xl px-4 py-3 text-left",
                    mode === "full_project_rewrite"
                      ? "bg-white shadow-sm ring-1 ring-amber-200"
                      : "hover:bg-white",
                  )}
                >
                  <span className="font-black text-slate-950">全项目重构</span>
                  <span className="mt-1 block text-xs text-slate-500">生成完整新版圣经，适合类型/主线大改。</span>
                </button>
              </div>
              <div className="mt-3 grid gap-2 text-sm text-slate-600">
                {starterPrompts.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    disabled={chat.isPending}
                    onClick={() => submitMessage(prompt)}
                    className="rounded-2xl bg-slate-50 px-4 py-3 text-left hover:bg-cyan-50 disabled:opacity-60"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={cn(
                    "rounded-3xl border p-4 text-sm shadow-sm",
                    message.role === "user"
                      ? "ml-10 border-cyan-100 bg-cyan-50"
                      : "mr-10 border-slate-200 bg-white",
                  )}
                >
                  <div className="mb-2 flex items-center gap-2 text-xs font-bold text-slate-500">
                    {message.role === "user" ? <UserRound className="size-3.5" /> : <Bot className="size-3.5" />}
                    {message.role === "user" ? "你" : "AI 编辑"}
                  </div>
                  <p className="whitespace-pre-wrap leading-6 text-slate-800">{message.content}</p>
                </div>
              ))}
              {chat.isPending ? (
                <div className="mr-10 rounded-3xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
                  <div className="mb-2 flex items-center gap-2 text-xs font-bold text-slate-500">
                    <Bot className="size-3.5" />
                    AI 编辑
                  </div>
                  <div className="flex items-center gap-2 text-slate-500">
                    <Loader2 className="size-4 animate-spin" />
                    正在整理本模块与联动修改提案...
                  </div>
                </div>
              ) : null}
              {backgroundJob && backgroundStatus !== "succeeded" ? (
                <div className="mr-10 rounded-3xl border border-amber-200 bg-amber-50 p-4 text-sm shadow-sm">
                  <div className="mb-2 flex items-center gap-2 text-xs font-bold text-amber-700">
                    <Bot className="size-3.5" />
                    后台生成
                  </div>
                  {backgroundStatus === "failed" ? (
                    <div className="text-amber-900">
                      <p className="font-black">全项目重构提案生成失败</p>
                      <p className="mt-1 text-sm">{backgroundError || "请重试。"}</p>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 text-amber-800">
                      <Loader2 className="size-4 animate-spin" />
                      正在后台生成完整故事圣经快照，任务 ID：{backgroundJob.id}
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          )}

          {messages.length > 0 && groups.length === 0 && !chat.isPending && backgroundStatus !== "queued" && backgroundStatus !== "running" ? (
            errorMessage || backgroundError ? (
              <div className="mt-5 rounded-3xl border border-red-200 bg-red-50 p-4">
                <div className="flex items-start gap-2">
                  <AlertCircle className="mt-0.5 size-4 text-red-600" />
                  <div>
                    <p className="font-black text-red-900">AI 优化失败</p>
                    <p className="mt-1 text-sm text-red-800">{errorMessage || backgroundError}</p>
                  </div>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  className="mt-3"
                  disabled={!lastUserMessage || chat.isPending}
                  onClick={() => submitMessage(lastUserMessage, mode)}
                >
                  <RefreshCw className="size-3.5" /> 重试
                </Button>
              </div>
            ) : (
              <div className="mt-5 rounded-3xl border border-amber-200 bg-amber-50 p-4">
                <p className="font-black text-amber-900">AI 只返回了建议，未生成可应用修改</p>
                <p className="mt-1 text-sm text-amber-800">
                  可以切到全项目重构，强制生成完整故事圣经快照。
                </p>
                <Button
                  type="button"
                  size="sm"
                  className="mt-3"
                  disabled={!lastUserMessage || chat.isPending}
                  onClick={() => {
                    setMode("full_project_rewrite");
                    submitMessage(lastUserMessage, "full_project_rewrite");
                  }}
                >
                  <RefreshCw className="size-3.5" /> 重新生成可应用修改
                </Button>
              </div>
            )
          ) : null}

          {groups.length > 0 ? (
            <div className="mt-5 space-y-3">
              <p className="text-xs font-black uppercase tracking-[0.18em] text-slate-400">可应用提案</p>
              {groups.map((group) => {
                const isGroupApply = Boolean(group.groupId);
                const bundleProposal = group.proposals.find(
                  (proposal) => proposal.target_type === "story_bible_bundle",
                );
                const actionKey = group.groupId ?? group.proposals[0]?.id ?? group.key;
                const isApplying =
                  applyingKey === actionKey ||
                  (!!bundleProposal && applyingKey === `rebuild:${bundleProposal.id}`);
                return (
                  <div key={group.key} className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="mb-2 flex flex-wrap gap-2">
                          <Badge tone={group.applied ? "green" : "amber"}>{group.applied ? "已应用" : "待确认"}</Badge>
                          {isGroupApply ? <Badge tone="violet">成组联动</Badge> : <Badge tone="slate">单条提案</Badge>}
                        </div>
                        <h3 className="font-black text-slate-950">{group.title}</h3>
                        <p className="mt-1 text-sm text-slate-500">
                          {isGroupApply ? `包含 ${group.proposals.length} 条修改，需一次性应用。` : "兼容旧提案，可单独应用。"}
                        </p>
                      </div>
                      {bundleProposal && !group.groupId ? (
                        <div className="flex flex-wrap gap-2">
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={group.applied || isApplying}
                            onClick={() => apply.mutate(bundleProposal.id)}
                          >
                            {group.applied ? <CheckCircle2 className="size-3.5" /> : <Sparkles className="size-3.5" />}
                            仅应用设定
                          </Button>
                          <Button
                            size="sm"
                            disabled={group.applied || isApplying}
                            onClick={() => applyWithRebuild.mutate(bundleProposal.id)}
                          >
                            {isApplying ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
                            应用并重构项目
                          </Button>
                        </div>
                      ) : (
                        <Button
                          size="sm"
                          variant={group.applied ? "secondary" : "primary"}
                          disabled={group.applied || isApplying}
                          onClick={() => {
                            if (group.groupId) {
                              applyGroup.mutate(group.groupId);
                            } else if (group.proposals[0]) {
                              apply.mutate(group.proposals[0].id);
                            }
                          }}
                        >
                          {group.applied ? (
                            <CheckCircle2 className="size-3.5" />
                          ) : isApplying ? (
                            <Loader2 className="size-3.5 animate-spin" />
                          ) : (
                            <Sparkles className="size-3.5" />
                          )}
                          {group.applied ? "已应用" : isGroupApply ? "应用整组" : "应用修改"}
                        </Button>
                      )}
                    </div>
                    {renderProposalList("当前模块修改", group.primary)}
                    {renderProposalList("联动修改", group.linked)}
                    {group.riskNotes.length > 0 ? (
                      <p className="mt-3 text-xs text-amber-700">风险提示：{group.riskNotes.join("；")}</p>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>

        <form onSubmit={send} className="border-t border-slate-200 bg-white p-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
            <span className="font-bold">优化模式</span>
            <select
              value={mode}
              onChange={(event) => setMode(event.target.value as RevisionMode)}
              className="h-8 rounded-xl border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700"
            >
              <option value="patch">局部优化</option>
              <option value="full_project_rewrite">全项目重构</option>
            </select>
          </div>
          <div className="rounded-3xl border border-slate-200 bg-slate-50 p-2">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              rows={3}
              placeholder="例如：只优化当前模块，但如果影响人物/世界观/大纲，请一起给出联动提案。"
              className="min-h-20 w-full resize-none bg-transparent px-3 py-2 text-sm outline-none"
            />
            <div className="flex justify-end">
              <Button type="submit" disabled={!input.trim() || chat.isPending}>
                {chat.isPending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
                {chat.isPending ? "思考中..." : "发送"}
              </Button>
            </div>
          </div>
        </form>
      </aside>
    </div>
  );
}
