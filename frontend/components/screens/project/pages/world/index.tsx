"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen, Boxes, Grid2X2, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProjectHeader } from "@/components/screens/project/project-frame";
import { worldItemsApi } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useScopedKey } from "@/lib/use-scoped-key";

type WorldFilter = "all" | "location" | "faction" | "rule";

const worldFilters: Array<{
  key: WorldFilter;
  title: string;
  description: string;
  icon: LucideIcon;
  tone: string;
}> = [
  {
    key: "all",
    title: "全部",
    description: "显示完整设定库",
    icon: Grid2X2,
    tone: "from-slate-500 to-slate-700",
  },
  {
    key: "location",
    title: "地点",
    description: "按 type=location 过滤",
    icon: Boxes,
    tone: "from-violet-500 to-indigo-600",
  },
  {
    key: "faction",
    title: "势力",
    description: "按 type=faction 过滤",
    icon: Users,
    tone: "from-blue-500 to-sky-600",
  },
  {
    key: "rule",
    title: "规则",
    description: "按 type=rule 过滤",
    icon: BookOpen,
    tone: "from-emerald-500 to-green-600",
  },
];

function normalizeWorldType(type: string) {
  const value = type.trim().toLowerCase();
  if (value === "organization") return "faction";
  return value;
}

function worldTypeLabel(type: string) {
  const value = normalizeWorldType(type);
  if (value === "location") return "地点";
  if (value === "faction") return "势力";
  if (value === "rule") return "规则";
  return type || "设定";
}

export function WorldPage({ projectId }: { projectId: string }) {
  const [activeFilter, setActiveFilter] = useState<WorldFilter>("all");
  const { data: items = [] } = useQuery({
    queryKey: useScopedKey("project", projectId, "world-items"),
    queryFn: () => worldItemsApi.list(projectId),
  });
  const filteredItems = useMemo(
    () =>
      activeFilter === "all"
        ? items
        : items.filter((item) => normalizeWorldType(item.type) === activeFilter),
    [activeFilter, items],
  );
  const countByFilter = useMemo(() => {
    return items.reduce<Record<WorldFilter, number>>(
      (acc, item) => {
        const type = normalizeWorldType(item.type);
        acc.all += 1;
        if (type === "location" || type === "faction" || type === "rule") {
          acc[type] += 1;
        }
        return acc;
      },
      { all: 0, location: 0, faction: 0, rule: 0 },
    );
  }, [items]);

  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <Card>
        <CardHeader>
          <CardTitle>设定库检索</CardTitle>
          <p className="mt-1 text-sm text-slate-500">
            地点、势力、规则会在故事圣经生成后写入 Lorebook，后续生成大纲、场景和正文时作为上下文。
          </p>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-4">
          {worldFilters.map((filter) => {
            const Icon = filter.icon;
            const active = activeFilter === filter.key;
            return (
              <button
                key={filter.key}
                type="button"
                onClick={() => setActiveFilter(filter.key)}
                className={cn(
                  "group flex items-center gap-4 rounded-2xl border bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md",
                  active ? "border-slate-950 ring-2 ring-slate-950/10" : "border-slate-200",
                )}
              >
                <div
                  className={cn(
                    "grid size-11 place-items-center rounded-2xl bg-gradient-to-br text-white",
                    filter.tone,
                  )}
                >
                  <Icon className="size-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-slate-950">{filter.title}</h3>
                    <Badge tone={active ? "blue" : "slate"}>{countByFilter[filter.key]}</Badge>
                  </div>
                  <p className="truncate text-sm text-slate-500">{filter.description}</p>
                </div>
              </button>
            );
          })}
        </CardContent>
      </Card>

      {items.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">
            尚无世界观条目，可先生成故事圣经，或在故事圣经页手动新增。
          </CardContent>
        </Card>
      ) : filteredItems.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">
            当前分类暂无条目，试试切换到“全部”，或在故事圣经页新增对应类型。
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {filteredItems.map((item) => (
            <Card key={item.id}>
              <CardContent>
                <Badge tone="blue">{worldTypeLabel(item.type)}</Badge>
                <h3 className="mt-3 text-lg font-black text-slate-950">{item.name}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-500">
                  {item.description.slice(0, 120)}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
