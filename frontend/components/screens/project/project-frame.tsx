"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, Play, ScrollText } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { projectsApi } from "@/lib/api";
import { ApiError } from "@/lib/http";
import { useScopedKey } from "@/lib/use-scoped-key";

/**
 * 项目页通用头部：面包屑 + 标题 + 状态徽标 + 顶部操作。
 *
 * 历史上这里曾有 9-tab 项目内导航，但当 StudioSidebar 在项目上下文中
 * 自动展开项目级菜单后，顶部 Tab 与侧边二级菜单重复且让视觉重心分散，
 * 已移除。导航完全由侧边栏承担。
 */
export function ProjectHeader({ projectId = "demo-project" }: { projectId?: string }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const { data: project } = useQuery({
    queryKey: useScopedKey("project", projectId),
    queryFn: () => projectsApi.get(projectId),
    enabled: !!user,
  });

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
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
          <Link href="/studio">工作台</Link>
          <span>/</span>
          <Link href="/studio/projects">项目</Link>
          <span>/</span>
          <span>加载中…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
        <Link href="/studio" className="hover:text-slate-900">
          工作台
        </Link>
        <span>/</span>
        <Link href="/studio/projects" className="hover:text-slate-900">
          项目
        </Link>
        <span>/</span>
        <span className="font-semibold text-slate-700">{project.title}</span>
      </div>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
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
    </div>
  );
}

