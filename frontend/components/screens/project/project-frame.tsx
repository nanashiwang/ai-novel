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
 * 主操作按钮根据 project.status 动态选择 CTA，避免在 bible_ready 阶段
 * 仍硬编码"继续生成下一章"造成误导。
 */

type CtaConfig = {
  label: string;
  hint: string;
  /** "submit" 走 generateFullNovel；"link" 单纯跳转。 */
  kind: "submit" | "link";
  href_suffix?: string;
};

const STATUS_CTA: Record<string, CtaConfig> = {
  created: {
    label: "生成故事圣经",
    hint: "去启动 generate_bible 任务",
    kind: "link",
    href_suffix: "/bible",
  },
  bible_generating: {
    label: "查看任务进度",
    hint: "故事圣经生成中",
    kind: "link",
    href_suffix: "/jobs",
  },
  bible_ready: {
    label: "生成章节大纲",
    hint: "去启动 generate_outline 任务",
    kind: "link",
    href_suffix: "/outline",
  },
  outline_generating: {
    label: "查看任务进度",
    hint: "章节大纲生成中",
    kind: "link",
    href_suffix: "/jobs",
  },
  outlined: {
    label: "拆分第 1 章场景",
    hint: "去启动 generate_scene_plan",
    kind: "link",
    href_suffix: "/outline",
  },
  scenes_planning: {
    label: "查看任务进度",
    hint: "场景计划生成中",
    kind: "link",
    href_suffix: "/jobs",
  },
  scenes_planned: {
    label: "生成第 1 个场景",
    hint: "去写作工作台",
    kind: "link",
    href_suffix: "/write",
  },
  drafting: {
    label: "继续生成下一章",
    hint: "立刻调度全书生成 pipeline",
    kind: "submit",
  },
  completed: {
    label: "导出全书",
    hint: "项目已完成",
    kind: "link",
    href_suffix: "/export",
  },
};

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

  const cta = STATUS_CTA[project.status] ?? STATUS_CTA.created;

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
          {cta.kind === "submit" ? (
            <Button onClick={() => generate.mutate()} disabled={generate.isPending}>
              <Play className="size-4" /> {generate.isPending ? "提交中…" : cta.label}
            </Button>
          ) : (
            <Link href={`/studio/projects/${project.id}${cta.href_suffix ?? ""}`}>
              <Button>
                <Play className="size-4" /> {cta.label}
              </Button>
            </Link>
          )}
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
      <p className="text-xs text-slate-400">{cta.hint}</p>
    </div>
  );
}

