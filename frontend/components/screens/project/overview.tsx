"use client";

import { AlertTriangle, BookOpen, CheckCircle2, FileClock, Gauge, GitBranch, Sparkles } from "lucide-react";
import { ProjectHeader } from "./project-frame";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { ProgressBar } from "@/components/ui/progress";
import { StatCard } from "@/components/ui/stat-card";
import { chapters, getProject, issues, jobs, workflowSteps } from "@/lib/mock-data";
import { formatNumber } from "@/lib/format";
import { WorkflowSteps } from "@/components/ui/workflow-steps";

export function ProjectOverviewPage({ projectId }: { projectId: string }) {
  const project = getProject(projectId);
  return (
    <div className="space-y-6">
      <ProjectHeader projectId={project.id} />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="项目状态" value="drafting" icon={GitBranch} tone="blue" />
        <StatCard label="章节进度" value={`${project.completedChapterCount}/${project.targetChapterCount}`} icon={BookOpen} tone="green" />
        <StatCard label="当前字数" value={formatNumber(project.currentWordCount)} icon={Gauge} tone="violet" />
        <StatCard label="审稿问题" value="27" icon={AlertTriangle} tone="orange" />
      </div>
      <Card>
        <CardHeader><CardTitle>项目状态机</CardTitle></CardHeader>
        <CardContent>
          <WorkflowSteps steps={workflowSteps.map((step) => step.name === "生成正文" ? { ...step, name: "正文 drafting" } : step)} />
        </CardContent>
      </Card>
      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <CardHeader><CardTitle>章节进度</CardTitle></CardHeader>
          <CardContent>
            <DataTable
              rows={chapters}
              columns={[
                { key: "chapter", header: "章节", render: (row) => <span className="font-bold text-slate-950">第{row.chapterIndex}章 · {row.title}</span> },
                { key: "goal", header: "目标", render: (row) => row.goal },
                { key: "status", header: "状态", render: (row) => <StatusBadge status={row.status} /> },
                { key: "progress", header: "进度", render: (row) => <div className="min-w-36"><ProgressBar value={row.progress} tone="green" /><p className="mt-1 text-xs text-slate-500">{row.progress}% · {row.wordCount.toLocaleString()} 字</p></div> },
              ]}
            />
          </CardContent>
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle>最近生成任务</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {jobs.slice(0, 3).map((job) => <div key={job.id} className="rounded-2xl border border-slate-200 p-4"><div className="flex justify-between gap-3"><p className="font-bold text-slate-950">{job.title}</p><StatusBadge status={job.status} /></div><ProgressBar value={job.progress} className="mt-3" /><p className="mt-2 text-xs text-slate-500">额度预留 {job.reservedQuota.toLocaleString()} · 当前步骤 {job.currentStep}</p></div>)}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>最近审稿问题</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {issues.map((issue) => <div key={issue.id} className="flex items-start gap-3 rounded-2xl bg-slate-50 p-3"><AlertTriangle className="mt-0.5 size-4 text-orange-500" /><div><p className="font-semibold text-slate-950">{issue.title}</p><p className="text-xs text-slate-500">{issue.suggestion}</p></div><Badge tone={issue.severity === "high" ? "rose" : "amber"}>{issue.severity}</Badge></div>)}
            </CardContent>
          </Card>
        </div>
      </div>
      <Card>
        <CardContent className="grid gap-4 md:grid-cols-3">
          <div className="flex items-center gap-3"><CheckCircle2 className="size-5 text-emerald-600" /><span className="font-semibold text-slate-700">Auth / Tenant / Permission 已通过 mock 检查</span></div>
          <div className="flex items-center gap-3"><Sparkles className="size-5 text-indigo-600" /><span className="font-semibold text-slate-700">Entitlement：Pro 支持长篇自动生成</span></div>
          <div className="flex items-center gap-3"><FileClock className="size-5 text-orange-600" /><span className="font-semibold text-slate-700">Quota Reservation：生成前预留，完成后结算</span></div>
        </CardContent>
      </Card>
    </div>
  );
}
