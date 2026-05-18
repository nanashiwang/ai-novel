"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, BookOpen, CheckCircle2, FileClock, Gauge, GitBranch, Sparkles } from "lucide-react";

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
