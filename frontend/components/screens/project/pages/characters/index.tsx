"use client";

import { useQuery } from "@tanstack/react-query";
import { Network } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProjectHeader } from "@/components/screens/project/project-frame";
import { BibleBlock } from "@/components/screens/project/shared/bible-block";
import { charactersApi } from "@/lib/api";
import { useScopedKey } from "@/lib/use-scoped-key";

function formatCharacterState(state?: Record<string, unknown>) {
  if (!state || Object.keys(state).length === 0) return "—";
  return Object.entries(state)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join("\n");
}

export function CharactersPage({ projectId }: { projectId: string }) {
  const { data: characters = [] } = useQuery({
    queryKey: useScopedKey("project", projectId, "characters"),
    queryFn: () => charactersApi.list(projectId),
  });
  const [activeId, setActiveId] = useState<string | null>(null);
  const active = characters.find((c) => c.id === activeId) ?? characters[0];

  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <div className="grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
        <Card>
          <CardHeader>
            <CardTitle>人物列表</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {characters.length === 0 ? (
              <p className="py-8 text-center text-sm text-slate-500">暂无人物，去创建吧。</p>
            ) : (
              characters.map((character) => (
                <button
                  key={character.id}
                  type="button"
                  onClick={() => setActiveId(character.id)}
                  className={`w-full rounded-2xl border p-4 text-left transition ${
                    active?.id === character.id
                      ? "border-indigo-300 bg-indigo-50"
                      : "border-slate-200 hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <p className="font-bold text-slate-950">{character.name}</p>
                    <Badge tone="violet">{character.role || "未定义"}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-slate-500">
                    {character.description?.slice(0, 80) || "—"}
                  </p>
                </button>
              ))
            )}
          </CardContent>
        </Card>
        <div className="space-y-4">
          {active ? (
            <Card>
              <CardHeader>
                <CardTitle>人物详情：{active.name}</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 md:grid-cols-2">
                <BibleBlock title="动机" text={active.motivation || "—"} />
                <BibleBlock title="秘密" text={active.secret || "—"} />
                <BibleBlock title="性格" text={active.personality || "—"} />
                <BibleBlock title="弧光" text={active.arc || "—"} />
                <BibleBlock title="角色定位" text={active.role || "—"} />
                <BibleBlock title="描述" text={active.description || "—"} />
                <BibleBlock title="当前状态" text={formatCharacterState(active.current_state)} />
              </CardContent>
            </Card>
          ) : null}
          <Card>
            <CardHeader>
              <CardTitle>人物关系图</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-3">
                {characters.map((character) => (
                  <div
                    key={character.id}
                    className="rounded-2xl border border-slate-200 bg-white p-4 text-center"
                  >
                    <div className="mx-auto grid size-12 place-items-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 text-lg font-black text-white">
                      {character.name.slice(0, 1)}
                    </div>
                    <p className="mt-2 font-bold text-slate-950">{character.name}</p>
                    <p className="text-xs text-slate-500">{character.role}</p>
                  </div>
                ))}
              </div>
              <div className="mt-4 rounded-2xl bg-slate-50 p-4 text-sm text-slate-600">
                <Network className="mr-2 inline size-4 text-indigo-600" />
                关系边由 Memory Engine 自动写入。
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
