"use client";

import { useMutation } from "@tanstack/react-query";
import { Bot, CheckCircle2, Loader2, Send, Sparkles, UserRound, X } from "lucide-react";
import { type FormEvent, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  type RevisionMessage,
  type RevisionProposal,
  revisionApi,
} from "@/lib/api";
import { ApiError } from "@/lib/http";
import { cn } from "@/lib/cn";

const targetLabel: Record<string, string> = {
  project_settings: "项目设置",
  story_bible: "故事圣经",
  character: "人物",
  world_item: "世界观",
  plot_thread: "剧情线",
};

function formatValue(value: unknown): string {
  if (Array.isArray(value)) return value.join("、");
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value ?? "");
}

export type RevisionCopilotDrawerProps = {
  projectId: string;
  onClose: () => void;
  onApplied: () => void;
};

export function RevisionCopilotDrawer({
  projectId,
  onClose,
  onApplied,
}: RevisionCopilotDrawerProps) {
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<RevisionMessage[]>([]);
  const [proposals, setProposals] = useState<RevisionProposal[]>([]);
  const [applyingId, setApplyingId] = useState<string | null>(null);

  const chat = useMutation({
    mutationFn: (message: string) =>
      revisionApi.chat(projectId, {
        message,
        session_id: sessionId,
        scope: "story_bible",
      }),
    onSuccess: (data) => {
      setSessionId(data.session.id);
      setMessages(data.messages);
      setProposals((prev) => {
        const seen = new Set(prev.map((item) => item.id));
        return [...prev, ...data.proposals.filter((item) => !seen.has(item.id))];
      });
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "AI 优化失败"),
  });

  const apply = useMutation({
    mutationFn: (proposalId: string) => revisionApi.applyProposal(projectId, proposalId),
    onMutate: (proposalId) => setApplyingId(proposalId),
    onSuccess: (data) => {
      setProposals((prev) =>
        prev.map((item) => (item.id === data.proposal.id ? data.proposal : item)),
      );
      onApplied();
      toast.success("提案已应用");
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "应用失败"),
    onSettled: () => setApplyingId(null),
  });

  const send = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const message = input.trim();
    if (!message || chat.isPending) return;
    setInput("");
    chat.mutate(message);
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
                <Sparkles className="size-3.5" /> AI 设定共创
              </div>
              <h2 className="mt-3 text-xl font-black">优化故事圣经与设定资产</h2>
              <p className="mt-1 text-sm text-slate-300">
                AI 只生成修改提案；点击「应用修改」后才会写入项目。
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
              <p className="font-black text-slate-950">可以这样问：</p>
              <div className="mt-3 grid gap-2 text-sm text-slate-600">
                <button
                  type="button"
                  onClick={() => setInput("请检查故事圣经、人物和世界观，找出最值得优化的 3 个设定点。")}
                  className="rounded-2xl bg-slate-50 px-4 py-3 text-left hover:bg-cyan-50"
                >
                  请检查故事圣经、人物和世界观，找出最值得优化的 3 个设定点。
                </button>
                <button
                  type="button"
                  onClick={() => setInput("帮我强化主角动机，并补一条能贯穿长篇的世界硬规则。")}
                  className="rounded-2xl bg-slate-50 px-4 py-3 text-left hover:bg-cyan-50"
                >
                  帮我强化主角动机，并补一条能贯穿长篇的世界硬规则。
                </button>
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
                    {message.role === "user" ? (
                      <UserRound className="size-3.5" />
                    ) : (
                      <Bot className="size-3.5" />
                    )}
                    {message.role === "user" ? "你" : "AI 编辑"}
                  </div>
                  <p className="whitespace-pre-wrap leading-6 text-slate-800">{message.content}</p>
                </div>
              ))}
            </div>
          )}

          {proposals.length > 0 ? (
            <div className="mt-5 space-y-3">
              <p className="text-xs font-black uppercase tracking-[0.18em] text-slate-400">
                可应用提案
              </p>
              {proposals.map((proposal) => (
                <div
                  key={proposal.id}
                  className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="mb-2 flex flex-wrap gap-2">
                        <Badge tone={proposal.status === "applied" ? "green" : "amber"}>
                          {proposal.status === "applied" ? "已应用" : "待确认"}
                        </Badge>
                        <Badge tone="blue">{targetLabel[proposal.target_type] ?? proposal.target_type}</Badge>
                        <Badge tone="slate">{proposal.action === "create" ? "新增" : "更新"}</Badge>
                      </div>
                      <h3 className="font-black text-slate-950">{proposal.title}</h3>
                      <p className="mt-1 text-sm text-slate-500">{proposal.reason}</p>
                    </div>
                    <Button
                      size="sm"
                      variant={proposal.status === "applied" ? "secondary" : "primary"}
                      disabled={proposal.status === "applied" || applyingId === proposal.id}
                      onClick={() => apply.mutate(proposal.id)}
                    >
                      {proposal.status === "applied" ? (
                        <CheckCircle2 className="size-3.5" />
                      ) : applyingId === proposal.id ? (
                        <Loader2 className="size-3.5 animate-spin" />
                      ) : (
                        <Sparkles className="size-3.5" />
                      )}
                      {proposal.status === "applied" ? "已应用" : "应用修改"}
                    </Button>
                  </div>
                  <div className="mt-3 rounded-2xl bg-slate-50 p-3">
                    {Object.entries(proposal.patch).map(([key, value]) => (
                      <div key={key} className="grid gap-1 py-1 text-sm md:grid-cols-[140px_1fr]">
                        <span className="font-bold text-slate-500">{key}</span>
                        <span className="break-words text-slate-800">{formatValue(value)}</span>
                      </div>
                    ))}
                  </div>
                  {proposal.impact.length > 0 ? (
                    <p className="mt-2 text-xs text-slate-400">
                      影响范围：{proposal.impact.join("、")}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </div>

        <form onSubmit={send} className="border-t border-slate-200 bg-white p-4">
          <div className="rounded-3xl border border-slate-200 bg-slate-50 p-2">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              rows={3}
              placeholder="例如：检查人物动机是否足够支撑 750 章，并提出可应用修改。"
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
