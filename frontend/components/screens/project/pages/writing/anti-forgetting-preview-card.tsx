"use client";

import { ChevronDown, ChevronUp, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  type AntiForgettingPreviewResponse,
  type ChapterStateRequirement,
  type StoryStateItem,
} from "@/lib/api";

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

function requirementOriginLabel(requirement: ChapterStateRequirement) {
  if (requirement.origin_type === "manual") return "人工添加";
  if (requirement.origin_type === "previous_chapter_carryover") {
    return requirement.source_chapter_index != null
      ? `来自第 ${requirement.source_chapter_index} 章`
      : "来自前文";
  }
  if (requirement.origin_type === "backfill") return "历史补全";
  return "本章提取";
}

function stateKindLabel(state: StoryStateItem) {
  const hard = state.is_hard_constraint ? "硬约束 · " : "";
  return `${hard}${state.entity_type}/${state.state_type} · P${state.priority}`;
}

export function AntiForgettingPreviewCard({
  preview,
  isPending,
  onSelectState,
}: {
  preview?: AntiForgettingPreviewResponse;
  isPending: boolean;
  onSelectState: (state: StoryStateItem) => void;
}) {
  const [showPrompt, setShowPrompt] = useState(false);
  const stateById = useMemo(
    () => new Map((preview?.story_states ?? []).map((item) => [item.id, item])),
    [preview?.story_states],
  );
  const requirementCount = preview?.meta.anti_forgetting_requirement_count ?? 0;
  const stateCount = preview?.meta.anti_forgetting_state_count ?? 0;
  const hasPreview = requirementCount > 0 || stateCount > 0;

  return (
    <div className="border-b border-slate-100 px-5 py-3">
      <div className="rounded-2xl border border-emerald-100 bg-gradient-to-r from-emerald-50 via-teal-50/70 to-white p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="grid size-8 place-items-center rounded-xl bg-emerald-600 text-white shadow-sm">
              <ShieldCheck className="size-4" />
            </div>
            <div>
              <p className="text-sm font-black text-emerald-950">写作前防遗忘注入</p>
              <p className="text-xs text-emerald-800/80">
                生成正文前会把这些状态和承接要求放进 prompt。
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={requirementCount > 0 ? "amber" : "slate"}>
              承接要求 {requirementCount}
            </Badge>
            <Badge tone={stateCount > 0 ? "green" : "slate"}>
              关键设定 {stateCount}
            </Badge>
            {preview?.prompt_block ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setShowPrompt((value) => !value)}
              >
                {showPrompt ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
                {showPrompt ? "收起文本" : "查看注入文本"}
              </Button>
            ) : null}
          </div>
        </div>

        {isPending ? (
          <p className="mt-3 text-xs text-emerald-800">正在计算本场景注入内容…</p>
        ) : !hasPreview ? (
          <p className="mt-3 text-xs text-slate-500">
            当前场景暂未匹配到承接要求或高风险关键设定；如果担心偏移，可以先在大纲页人工添加承接要求。
          </p>
        ) : (
          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            <div className="rounded-xl border border-white/70 bg-white/80 p-3">
              <p className="text-xs font-black text-slate-950">本章承接要求</p>
              {preview?.requirements.length ? (
                <div className="mt-2 space-y-2">
                  {preview.requirements.slice(0, 4).map((requirement) => {
                    const linkedState =
                      requirement.state_item ?? stateById.get(requirement.state_item_id);
                    return (
                      <div key={requirement.id} className="rounded-lg bg-amber-50/70 p-2">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <Badge tone={requirementTone(requirement.requirement_type)}>
                            {requirementTypeLabel[requirement.requirement_type] ??
                              requirement.requirement_type}
                          </Badge>
                          <Badge tone={requirement.origin_type === "manual" ? "orange" : "slate"}>
                            {requirementOriginLabel(requirement)}
                          </Badge>
                          {requirement.source_issue_id ? (
                            <Badge tone="rose">来自审稿</Badge>
                          ) : null}
                          <span className="text-[11px] font-semibold text-slate-400">
                            P{requirement.priority}
                          </span>
                        </div>
                        <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-700">
                          {requirement.summary || "—"}
                        </p>
                        {linkedState ? (
                          <button
                            type="button"
                            onClick={() => onSelectState(linkedState)}
                            className="mt-1 text-xs font-semibold text-emerald-700 hover:text-emerald-900"
                          >
                            关联设定：{linkedState.name}
                          </button>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="mt-2 text-xs text-slate-500">暂无本章承接要求。</p>
              )}
            </div>

            <div className="rounded-xl border border-white/70 bg-white/80 p-3">
              <p className="text-xs font-black text-slate-950">关键设定</p>
              {preview?.story_states.length ? (
                <div className="mt-2 space-y-2">
                  {preview.story_states.slice(0, 5).map((state) => (
                    <button
                      key={state.id}
                      type="button"
                      onClick={() => onSelectState(state)}
                      className="block w-full rounded-lg bg-slate-50 p-2 text-left transition hover:bg-emerald-50"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className="truncate text-xs font-bold text-slate-950">{state.name}</p>
                        <Badge tone={state.is_hard_constraint ? "rose" : "slate"}>
                          {state.status}
                        </Badge>
                      </div>
                      <p className="mt-1 text-[11px] font-semibold text-slate-400">
                        {stateKindLabel(state)}
                      </p>
                      <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-600">
                        {state.summary || "—"}
                      </p>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="mt-2 text-xs text-slate-500">暂无可注入关键设定。</p>
              )}
            </div>
          </div>
        )}

        {showPrompt && preview?.prompt_block ? (
          <pre className="mt-3 max-h-52 overflow-auto rounded-xl border border-emerald-100 bg-white/90 p-3 text-xs leading-5 text-slate-700">
            {preview.prompt_block}
          </pre>
        ) : null}
      </div>
    </div>
  );
}
