"use client";

import { useQuery } from "@tanstack/react-query";
import { BrainCircuit, Clock3, Search, UserRound } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProjectHeader } from "@/components/screens/project/project-frame";
import { type MemoryEntry, memoryApi } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useScopedKey } from "@/lib/use-scoped-key";

type MemoryFilter = "all" | "scene_plan" | "character_state";

const memoryFilters: Array<{ key: MemoryFilter; label: string; hint: string }> = [
  { key: "all", label: "全部", hint: "完整记忆流" },
  { key: "scene_plan", label: "场景摘要", hint: "按时间回看剧情" },
  { key: "character_state", label: "人物状态", hint: "角色变化与关系" },
];

function memoryLabel(type: string) {
  if (type === "scene_plan") return "场景摘要";
  if (type === "character_state") return "人物状态";
  if (type === "chapter_summary") return "章节摘要";
  if (type === "world_rule") return "世界规则";
  return type || "记忆";
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function groupByType(entries: MemoryEntry[]) {
  return entries.reduce<Record<string, number>>((acc, entry) => {
    acc[entry.memory_type] = (acc[entry.memory_type] ?? 0) + 1;
    return acc;
  }, {});
}

export function MemoryPage({ projectId }: { projectId: string }) {
  const [activeFilter, setActiveFilter] = useState<MemoryFilter>("all");
  const [query, setQuery] = useState("");
  const [character, setCharacter] = useState("");
  const { data: memories = [], isPending } = useQuery({
    queryKey: useScopedKey("project", projectId, "memory", activeFilter, query, character),
    queryFn: () =>
      memoryApi.list(projectId, {
        memory_type: activeFilter === "all" ? undefined : activeFilter,
        q: query.trim() || undefined,
        character: character.trim() || undefined,
        limit: 100,
      }),
  });
  const countByType = useMemo(() => groupByType(memories), [memories]);
  const selected = memories[0];

  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <Card className="overflow-hidden border-slate-200">
        <CardHeader className="bg-gradient-to-br from-slate-950 via-slate-800 to-cyan-900 text-white">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <CardTitle className="flex items-center gap-2 text-white">
                <BrainCircuit className="size-5" /> Memory Engine
              </CardTitle>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-200">
                写完 scene 后自动沉淀场景摘要与人物状态；ContextBuilder 会按角色和时间把相关记忆召回给后续生成。
              </p>
            </div>
            <Badge tone="blue">{memories.length} 条记忆</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 p-5">
          <div className="grid gap-3 md:grid-cols-3">
            {memoryFilters.map((filter) => {
              const active = activeFilter === filter.key;
              const count =
                filter.key === "all" ? memories.length : countByType[filter.key] ?? 0;
              return (
                <button
                  key={filter.key}
                  type="button"
                  onClick={() => setActiveFilter(filter.key)}
                  className={cn(
                    "rounded-2xl border p-4 text-left transition hover:-translate-y-0.5 hover:shadow-md",
                    active ? "border-cyan-500 bg-cyan-50" : "border-slate-200 bg-white",
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-bold text-slate-950">{filter.label}</p>
                    <Badge tone={active ? "blue" : "slate"}>{count}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-slate-500">{filter.hint}</p>
                </button>
              );
            })}
          </div>
          <div className="grid gap-3 md:grid-cols-[1fr_1fr]">
            <label className="relative block">
              <Search className="absolute left-3 top-3 size-4 text-slate-400" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索记忆内容"
                className="w-full rounded-2xl border border-slate-200 bg-white py-2.5 pl-10 pr-3 text-sm outline-none focus:border-cyan-500"
              />
            </label>
            <label className="relative block">
              <UserRound className="absolute left-3 top-3 size-4 text-slate-400" />
              <input
                value={character}
                onChange={(event) => setCharacter(event.target.value)}
                placeholder="按人物名召回，例如：林澈"
                className="w-full rounded-2xl border border-slate-200 bg-white py-2.5 pl-10 pr-3 text-sm outline-none focus:border-cyan-500"
              />
            </label>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[1fr_0.8fr]">
        <Card>
          <CardHeader>
            <CardTitle>记忆流</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {isPending ? <p className="text-sm text-slate-500">加载中…</p> : null}
            {!isPending && memories.length === 0 ? (
              <p className="rounded-2xl bg-slate-50 p-6 text-center text-sm text-slate-500">
                暂无记忆。生成或重写 scene 后会自动写入。
              </p>
            ) : null}
            {memories.map((entry) => (
              <article key={entry.id} className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={entry.memory_type === "character_state" ? "blue" : "slate"}>
                      {memoryLabel(entry.memory_type)}
                    </Badge>
                    <p className="font-bold text-slate-950">{entry.title}</p>
                  </div>
                  <span className="inline-flex items-center gap-1 text-xs text-slate-400">
                    <Clock3 className="size-3" /> {formatDate(entry.created_at)}
                  </span>
                </div>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-600">
                  {entry.content}
                </p>
              </article>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>召回说明</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm leading-6 text-slate-600">
            <p>
              当前版本先接入数据库级角色/时间召回：人物状态记忆优先，其次按创建时间倒序补足上下文。
            </p>
            <p>
              下一步可把同一输出接到 pgvector HNSW，把语义相近的伏笔、地点、人物状态也召回。
            </p>
            {selected ? (
              <div className="rounded-2xl bg-slate-50 p-4">
                <p className="font-bold text-slate-950">最近记忆</p>
                <p className="mt-2 whitespace-pre-wrap">{selected.content}</p>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
