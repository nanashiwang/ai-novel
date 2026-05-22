"use client";

import { useMutation } from "@tanstack/react-query";
import { Bot, CheckCircle2, Loader2, Send, Sparkles, UserRound, X } from "lucide-react";
import { type FormEvent, useCallback, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import {
  type RevisionMessage,
  type RevisionProposal,
  type RevisionTargetType,
  revisionApi,
} from "@/lib/api";
import { ApiError } from "@/lib/http";

const targetLabel: Record<string, string> = {
  project_settings: "项目设置",
  story_bible: "核心设定",
  character: "人物",
  world_item: "世界观",
  plot_thread: "剧情线",
  chapter: "章节大纲",
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

export type RevisionCopilotDrawerProps = {
  projectId: string;
  scope: string;
  targetType?: RevisionTargetType | null;
  targetId?: string | null;
  title: string;
  description?: string;
  starterPrompts: string[];
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
  onClose,
  onApplied,
}: RevisionCopilotDrawerProps) {
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<RevisionMessage[]>([]);
  const [proposals, setProposals] = useState<RevisionProposal[]>([]);
  const [applyingKey, setApplyingKey] = useState<string | null>(null);

  const chat = useMutation({
    mutationFn: ({ message, currentSessionId }: { message: string; currentSessionId: string | null }) =>
      revisionApi.chat(projectId, {
        message,
        session_id: currentSessionId,
        scope,
        target_type: targetType,
        target_id: targetId,
      }),
    onSuccess: (data) => {
      setSessionId(data.session.id);
      setMessages(data.messages);
      setProposals(data.proposals);
      if (data.proposals.length === 0) {
        toast.warning("AI 返回了分析，但没有生成可应用修改");
      }
    },
    onError: (e: unknown) => {
      setMessages((prev) => prev.filter((item) => !item.id.startsWith("optimistic-")));
      toast.error(e instanceof ApiError ? e.message : "AI 优化失败");
    },
  });

  const submitMessage = useCallback(
    (rawMessage: string) => {
      const message = rawMessage.trim();
      if (!message || chat.isPending) return;
      setInput("");
      setProposals([]);
      setMessages((prev) => [
        ...prev,
        {
          id: `optimistic-${Date.now()}`,
          session_id: sessionId ?? "",
          role: "user",
          content: message,
        },
      ]);
      chat.mutate({ message, currentSessionId: sessionId });
    },
    [chat, sessionId],
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

  const send = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    submitMessage(input);
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
              <div className="mt-2 space-y-1">
                {Object.entries(proposal.patch).map(([key, value]) => (
                  <div key={key} className="grid gap-1 text-sm md:grid-cols-[120px_1fr]">
                    <span className="font-bold text-slate-500">{key}</span>
                    <span className="break-words text-slate-800">{formatValue(value)}</span>
                  </div>
                ))}
              </div>
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
              <p className="font-black text-slate-950">先输入你的优化目标，或点一个示例：</p>
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
            </div>
          )}

          {groups.length > 0 ? (
            <div className="mt-5 space-y-3">
              <p className="text-xs font-black uppercase tracking-[0.18em] text-slate-400">可应用提案</p>
              {groups.map((group) => {
                const isGroupApply = Boolean(group.groupId);
                const actionKey = group.groupId ?? group.proposals[0]?.id ?? group.key;
                const isApplying = applyingKey === actionKey;
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
