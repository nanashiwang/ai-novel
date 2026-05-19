"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  FileClock,
  FileDown,
  Gauge,
  GitBranch,
  Layers3,
  PenLine,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import type { LucideIcon } from "lucide-react";

import { ProjectHeader } from "./project-frame";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { ProgressBar } from "@/components/ui/progress";
import { StatCard } from "@/components/ui/stat-card";
import { chaptersApi, jobsApi, projectsApi } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { useScopedKey } from "@/lib/use-scoped-key";

// Chapter 的运行时形状（来自后端 schema）
type ChapterRow = {
  id: string;
  chapter_index: number;
  title: string;
  goal: string;
  status: string;
};

type JobRow = {
  id: string;
  job_type: string;
  status: string;
  workflow_id: string | null;
  reserved_quota: number;
  consumed_quota: number;
};

// 单一真相源：project.status → 下一步可点击动作。
// "等待中" 的过渡态把 CTA 指向 /jobs，让用户能直接看到任务进度而不是空白页。
type NextAction = {
  title: string;
  description: string;
  cta: string;
  hrefSuffix: string;
  icon: LucideIcon;
  waiting?: boolean;
};

const NEXT_ACTION_BY_STATUS: Record<string, NextAction> = {
  created: {
    title: "下一步：生成故事圣经",
    description: "提交 generate_bible 任务，预留额度并生成核心设定。",
    cta: "前往故事圣经",
    hrefSuffix: "/bible",
    icon: Sparkles,
  },
  bible_generating: {
    title: "故事圣经生成中",
    description: "等待 generate_bible 任务完成，可在任务页查看进度。",
    cta: "查看任务进度",
    hrefSuffix: "/jobs",
    icon: RefreshCw,
    waiting: true,
  },
  bible_ready: {
    title: "下一步：生成章节大纲",
    description: "依赖故事圣经，规划三幕推进与每章目标/冲突/钩子。",
    cta: "前往大纲页",
    hrefSuffix: "/outline",
    icon: Layers3,
  },
  outline_generating: {
    title: "章节大纲生成中",
    description: "等待 generate_outline 任务完成。",
    cta: "查看任务进度",
    hrefSuffix: "/jobs",
    icon: RefreshCw,
    waiting: true,
  },
  outlined: {
    title: "下一步：拆分场景计划",
    description: "把每章拆成 scene cards（Sprint 3 接入）。",
    cta: "前往大纲页",
    hrefSuffix: "/outline",
    icon: Layers3,
  },
  scenes_planning: {
    title: "场景计划生成中",
    description: "等待 generate_scene_plan 任务完成。",
    cta: "查看任务进度",
    hrefSuffix: "/jobs",
    icon: RefreshCw,
    waiting: true,
  },
  scenes_planned: {
    title: "下一步：进入写作工作台",
    description: "按场景生成正文草稿（Sprint 4 接入）。",
    cta: "前往写作",
    hrefSuffix: "/write",
    icon: PenLine,
  },
  drafting: {
    title: "继续写作",
    description: "已有草稿，可继续按场景生成或编辑。",
    cta: "前往写作",
    hrefSuffix: "/write",
    icon: PenLine,
  },
  completed: {
    title: "下一步：导出或审稿",
    description: "全书草稿完成，可触发导出或进入审稿。",
    cta: "前往导出",
    hrefSuffix: "/export",
    icon: FileDown,
  },
};

function NextActionCard({ projectId, status }: { projectId: string; status: string }) {
  const action = NEXT_ACTION_BY_STATUS[status];
  if (!action) return null;
  const Icon = action.icon;
  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="flex items-center gap-3">
          <div
            className={`rounded-2xl p-2 ${
              action.waiting ? "bg-amber-50 text-amber-600" : "bg-indigo-50 text-indigo-600"
            }`}
          >
            <Icon className={`size-5 ${action.waiting ? "animate-spin" : ""}`} />
          </div>
          <div>
            <p className="font-bold text-slate-950">{action.title}</p>
            <p className="text-sm text-slate-500">{action.description}</p>
          </div>
        </div>
        <Link
          href={`/studio/projects/${projectId}${action.hrefSuffix}`}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm shadow-indigo-200 transition hover:bg-indigo-700"
        >
          {action.cta} <Sparkles className="size-4" />
        </Link>
      </CardContent>
    </Card>
  );
}

export function ProjectOverviewPage({ projectId }: { projectId: string }) {
  const { data: project } = useQuery({
    queryKey: useScopedKey("project", projectId),
    queryFn: () => projectsApi.get(projectId),
  });
  const { data: chapters = [] } = useQuery({
    queryKey: useScopedKey("project", projectId, "chapters"),
    queryFn: () => chaptersApi.list(projectId) as Promise<ChapterRow[]>,
  });
  const { data: jobs = [] } = useQuery({
    queryKey: useScopedKey("project", projectId, "jobs"),
    queryFn: () => jobsApi.list() as Promise<JobRow[]>,
  });

  const projectJobs = jobs.filter(
    (j) => "project_id" in j && (j as unknown as { project_id: string }).project_id === projectId,
  );

  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="项目状态" value={project?.status ?? "—"} icon={GitBranch} tone="blue" />
        <StatCard
          label="章节进度"
          value={`${project?.completed_chapter_count ?? 0}/${project?.target_chapter_count ?? 0}`}
          icon={BookOpen}
          tone="green"
        />
        <StatCard
          label="当前字数"
          value={formatNumber(project?.current_word_count ?? 0)}
          icon={Gauge}
          tone="violet"
        />
        <StatCard
          label="运行中任务"
          value={String(projectJobs.filter((j) => j.status === "running").length)}
          icon={AlertTriangle}
          tone="orange"
        />
      </div>

      {project ? <NextActionCard projectId={projectId} status={project.status} /> : null}

      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <CardHeader>
            <CardTitle>章节进度</CardTitle>
          </CardHeader>
          <CardContent>
            {chapters.length === 0 ? (
              <p className="py-8 text-center text-sm text-slate-500">尚未生成章节大纲。</p>
            ) : (
              <DataTable
                rows={chapters}
                columns={[
                  {
                    key: "chapter",
                    header: "章节",
                    render: (row) => (
                      <span className="font-bold text-slate-950">
                        第 {row.chapter_index} 章 · {row.title}
                      </span>
                    ),
                  },
                  { key: "goal", header: "目标", render: (row) => row.goal || "—" },
                  {
                    key: "status",
                    header: "状态",
                    render: (row) => <StatusBadge status={row.status as never} />,
                  },
                  {
                    key: "progress",
                    header: "进度",
                    render: () => (
                      <div className="min-w-36">
                        <ProgressBar value={0} tone="green" />
                      </div>
                    ),
                  },
                ]}
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>最近生成任务</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {projectJobs.slice(0, 3).map((job) => (
              <div key={job.id} className="rounded-2xl border border-slate-200 p-4">
                <div className="flex justify-between gap-3">
                  <p className="font-bold text-slate-950">{job.job_type}</p>
                  <StatusBadge status={job.status as never} />
                </div>
                <ProgressBar
                  value={(job.consumed_quota / Math.max(job.reserved_quota, 1)) * 100}
                  className="mt-3"
                />
                <p className="mt-2 text-xs text-slate-500">
                  额度预留 {job.reserved_quota.toLocaleString()} · workflow{" "}
                  {job.workflow_id ?? "—"}
                </p>
              </div>
            ))}
            {projectJobs.length === 0 ? (
              <p className="text-center text-sm text-slate-500">暂无相关任务。</p>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="grid gap-4 md:grid-cols-3">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="size-5 text-emerald-600" />
            <span className="font-semibold text-slate-700">
              Auth / Tenant / Permission 实际执行中
            </span>
          </div>
          <div className="flex items-center gap-3">
            <Sparkles className="size-5 text-indigo-600" />
            <span className="font-semibold text-slate-700">Entitlement 已从套餐特性解析</span>
          </div>
          <div className="flex items-center gap-3">
            <FileClock className="size-5 text-orange-600" />
            <span className="font-semibold text-slate-700">
              Quota Reservation 行锁：生成前预留，完成后结算
            </span>
          </div>
        </CardContent>
        <Badge tone="blue" className="ml-4 mb-4">
          后端 endpoint 已接入
        </Badge>
      </Card>
    </div>
  );
}
