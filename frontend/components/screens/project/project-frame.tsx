"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, Play, ScrollText } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs } from "@/components/ui/tabs";
import { projectsApi } from "@/lib/api";
import { ApiError } from "@/lib/http";
import { projectNav } from "@/lib/routes";
import { useScopedKey } from "@/lib/use-scoped-key";

export function ProjectHeader({ projectId = "demo-project" }: { projectId?: string }) {
  const pathname = usePathname();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const { data: project } = useQuery({
    queryKey: useScopedKey("project", projectId),
    queryFn: () => projectsApi.get(projectId),
    enabled: !!user,
  });

  const tabs = projectNav.map((item) => ({
    label: item.label,
    href: item.href.replace("demo-project", projectId),
  }));

  const generate = useMutation({
    mutationFn: () => projectsApi.generateFullNovel(projectId, 20000),
    onSuccess: () => {
      toast.success("已提交生成任务");
      queryClient.invalidateQueries({ queryKey: ["org"] });
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "提交失败");
    },
  });

  if (!project) {
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2 text-sm text-slate-500">
              <Link href="/studio">工作台</Link>
              <span>/</span>
              <Link href="/studio/projects">项目</Link>
              <span>/</span>
              <span>加载中…</span>
            </div>
          </div>
        </div>
        <Tabs tabs={tabs} activeHref={pathname} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2 text-sm text-slate-500">
            <Link href="/studio">工作台</Link>
            <span>/</span>
            <Link href="/studio/projects">项目</Link>
            <span>/</span>
            <span>{project.title}</span>
          </div>
          <h1 className="text-3xl font-black text-slate-950">{project.title}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge tone="blue">组织：{user?.organization_name}</Badge>
            <StatusBadge status={project.status as never} />
            <Badge tone="violet">目标 {project.target_chapter_count} 章</Badge>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => generate.mutate()} disabled={generate.isPending}>
            <Play className="size-4" /> {generate.isPending ? "提交中…" : "继续生成下一章"}
          </Button>
          <Link href={`/studio/projects/${project.id}/jobs`}>
            <Button variant="secondary">
              <ScrollText className="size-4" /> 查看 Workflow 日志
            </Button>
          </Link>
          <Button variant="ghost" onClick={() => toast.info("更多菜单待对接")}>
            <MoreHorizontal className="size-4" /> 更多
          </Button>
        </div>
      </div>
      <Tabs tabs={tabs} activeHref={pathname} />
    </div>
  );
}
