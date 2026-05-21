"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, History, Sparkles, UserRound } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type CharacterRevision,
  type CharacterRevisionSource,
  characterRevisionsApi,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useScopedKey } from "@/lib/use-scoped-key";

const sourceLabel: Record<CharacterRevisionSource, string> = {
  user_edit: "手动",
  copilot: "Copilot",
  ai_inferred: "AI 推演",
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
  if (value == null || value === "") return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value, null, 2);
}

function sourceIcon(source: CharacterRevisionSource) {
  if (source === "ai_inferred") return Sparkles;
  if (source === "copilot") return Bot;
  return UserRound;
}

export type CharacterTimelineProps = {
  projectId: string;
  characterId: string;
  characterName: string;
};

/**
 * 人物随章节演进的时间线。
 *
 * 按 character_revisions/timeline endpoint 返回的 chapter 桶渲染：
 * - 章节内：applied revisions 按时间升序铺开
 * - 未关联章节（手动编辑 / Copilot 提案）：放最下面一个"散落"桶
 */
export function CharacterTimeline({
  projectId,
  characterId,
  characterName,
}: CharacterTimelineProps) {
  const timelineKey = useScopedKey(
    "project",
    projectId,
    "character-timeline",
    characterId,
  );
  const { data: entries = [], isPending } = useQuery({
    queryKey: timelineKey,
    queryFn: () => characterRevisionsApi.timeline(projectId, characterId),
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <History className="size-4 text-indigo-600" /> {characterName} 演进时间线
          </CardTitle>
          <p className="mt-1 text-xs text-slate-500">
            人物字段的所有应用记录按章节聚合；AI 推演、Copilot 与手动编辑同轴呈现。
          </p>
        </div>
        <Badge tone="slate">{entries.length} 节点</Badge>
      </CardHeader>
      <CardContent>
        {isPending ? (
          <p className="py-6 text-center text-sm text-slate-500">加载中…</p>
        ) : entries.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-500">
            尚无演进记录。生成 / 写作场景后 AI 推演的状态变化会自动出现在此处。
          </p>
        ) : (
          <ol className="relative space-y-5 pl-5 before:absolute before:left-1.5 before:top-1 before:h-full before:w-px before:bg-slate-200">
            {entries.map((entry) => (
              <li key={entry.chapter_id ?? "unanchored"} className="relative">
                <span className="absolute -left-[19px] top-1.5 grid size-3 place-items-center rounded-full border-2 border-white bg-indigo-500 shadow" />
                <div className="mb-2 flex flex-wrap items-center gap-2 text-sm font-bold text-slate-950">
                  {entry.chapter_index != null ? (
                    <>
                      <span>第 {entry.chapter_index} 章</span>
                      <span className="text-slate-500">·</span>
                      <span className="text-slate-700">{entry.chapter_title || "—"}</span>
                    </>
                  ) : (
                    <span className="text-slate-700">未关联章节（手动 / 设定共创）</span>
                  )}
                  <Badge tone="slate">{entry.revisions.length}</Badge>
                </div>
                <ul className="space-y-2">
                  {entry.revisions.map((rev: CharacterRevision) => {
                    const Icon = sourceIcon(rev.source);
                    return (
                      <li
                        key={rev.id}
                        className="rounded-xl border border-slate-200 bg-white p-3 text-xs"
                      >
                        <div className="mb-1 flex flex-wrap items-center gap-2">
                          <Badge tone={rev.source === "ai_inferred" ? "violet" : "blue"}>
                            <Icon className="mr-1 inline size-3" /> {sourceLabel[rev.source]}
                          </Badge>
                          <span className="font-bold text-slate-800">
                            {fieldLabel[rev.field] ?? rev.field}
                          </span>
                          {rev.applied_at ? (
                            <span className="text-slate-400">
                              {formatDateTime(rev.applied_at)}
                            </span>
                          ) : null}
                        </div>
                        <div className="grid gap-1 md:grid-cols-2">
                          <div>
                            <p className="text-slate-500">旧值</p>
                            <pre className="mt-0.5 max-h-24 overflow-y-auto whitespace-pre-wrap rounded-md bg-slate-50 p-2 text-slate-600">
                              {formatValue(rev.old_value)}
                            </pre>
                          </div>
                          <div>
                            <p className="text-slate-500">新值</p>
                            <pre className="mt-0.5 max-h-24 overflow-y-auto whitespace-pre-wrap rounded-md bg-emerald-50 p-2 text-slate-800">
                              {formatValue(rev.new_value)}
                            </pre>
                          </div>
                        </div>
                        {rev.reason ? (
                          <p className="mt-2 text-slate-500 italic">依据：{rev.reason}</p>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
