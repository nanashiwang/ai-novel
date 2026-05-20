"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen, Boxes, Users } from "lucide-react";

import { ActionCard } from "@/components/ui/action-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProjectHeader } from "@/components/screens/project/project-frame";
import { worldItemsApi } from "@/lib/api";
import { useScopedKey } from "@/lib/use-scoped-key";

export function WorldPage({ projectId }: { projectId: string }) {
  const { data: items = [] } = useQuery({
    queryKey: useScopedKey("project", projectId, "world-items"),
    queryFn: () => worldItemsApi.list(projectId),
  });
  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      {items.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">
            尚无世界观条目，可在生成大纲时自动产出，或手动添加。
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {items.map((item) => (
            <Card key={item.id}>
              <CardContent>
                <Badge tone="blue">{item.type}</Badge>
                <h3 className="mt-3 text-lg font-black text-slate-950">{item.name}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-500">
                  {item.description.slice(0, 120)}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Lorebook 检索</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
          <ActionCard title="地点" description="按 type=location 过滤" href="#" icon={Boxes} tone="violet" />
          <ActionCard title="组织" description="按 type=organization 过滤" href="#" icon={Users} tone="blue" />
          <ActionCard title="规则" description="按 type=rule 过滤" href="#" icon={BookOpen} tone="green" />
        </CardContent>
      </Card>
    </div>
  );
}
