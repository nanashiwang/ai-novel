"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen, FileDown, Folder, Gauge, PenLine, Plus, ShieldAlert, Sparkles, Wand2, Zap } from "lucide-react";
import Link from "next/link";

import { useAuth } from "@/components/providers/auth-provider";
import { ActionCard } from "@/components/ui/action-card";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { ProgressBar } from "@/components/ui/progress";
import { StatCard } from "@/components/ui/stat-card";
import { jobsApi, projectsApi, quotaApi } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { isPlatformAdmin } from "@/lib/permissions";
import { useScopedKey } from "@/lib/use-scoped-key";

export function StudioDashboard() {
  const { user } = useAuth();
  const admin = isPlatformAdmin(user);

  const { data: projects = [] } = useQuery({
    queryKey: useScopedKey("projects"),
    queryFn: () => projectsApi.list(),
    enabled: !!user,
  });
  const { data: jobs = [] } = useQuery({
    queryKey: useScopedKey("generation-jobs"),
    queryFn: () => jobsApi.list(),
    enabled: !!user,
  });
  const { data: quotas = [] } = useQuery({
    queryKey: useScopedKey("quotas"),
    queryFn: () => quotaApi.list(),
    enabled: !!user,
  });

  const wordQuota = quotas.find((q) => q.quota_key === "monthly_generated_words");
  const runningJobs = jobs.filter((j) => j.status === "running" || j.status === "queued");

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black tracking-tight text-slate-950">创作工作台</h1>
          <p className="mt-1 text-slate-500">查看项目、生成任务、套餐额度与最近产出</p>
        </div>
        <Link href="/studio/projects/new">
          <Button size="lg">
            <Plus className="size-5" /> 新建项目
          </Button>
        </Link>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="当前项目" value={String(projects.length)} icon={Folder} tone="violet" />
        <StatCard
          label="本月已用字数"
          value={wordQuota ? formatNumber(wordQuota.used_value) : "0"}
          icon={Wand2}
          tone="blue"
        />
        <StatCard label="运行中任务" value={String(runningJobs.length)} icon={Zap} tone="green" />
        <StatCard
          label="任务总数"
          value={String(jobs.length)}
          icon={ShieldAlert}
          tone="orange"
        />
      </div>

      {admin ? (
        <Card className="border-indigo-200 bg-gradient-to-r from-indigo-50 via-white to-amber-50">
          <CardHeader className="flex flex-row items-center justify-between gap-3">
            <div>
              <CardTitle>管理员控制中心</CardTitle>
              <p className="mt-1 text-sm text-slate-500">
                super_admin 可见：平台级数据、套餐权益、队列和模型调用入口。
              </p>
            </div>
            <Badge tone="amber">仅平台管理员</Badge>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <ActionCard title="用户 / 组织" description="封禁、恢复、成员与组织状态" href="/admin/users" icon={BookOpen} tone="violet" />
            <ActionCard title="套餐权益" description="Plan、Feature、Entitlement" href="/admin/plans" icon={Gauge} tone="blue" />
            <ActionCard title="额度调整" description="手动调整并写入 audit_logs" href="/admin/quotas" icon={Zap} tone="orange" />
            <ActionCard title="任务队列" description="强制取消 / 重试 workflow" href="/admin/generation-jobs" icon={Sparkles} tone="green" />
            <ActionCard title="模型日志" description="Prompt / Response 摘要" href="/admin/model-calls" icon={FileDown} tone="violet" />
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>最近小说项目</CardTitle>
            <Link href="/studio/projects" className="text-sm font-semibold text-indigo-600">
              查看全部项目
            </Link>
          </CardHeader>
          <CardContent>
            {projects.length === 0 ? (
              <p className="py-8 text-center text-sm text-slate-500">还没有项目，去新建一个吧。</p>
            ) : (
              <DataTable
                rows={projects.slice(0, 6)}
                columns={[
                  {
                    key: "title",
                    header: "项目",
                    render: (row) => (
                      <Link
                        href={`/studio/projects/${row.id}`}
                        className="font-bold text-slate-950 hover:text-indigo-600"
                      >
                        {row.title}
                      </Link>
                    ),
                  },
                  { key: "genre", header: "类型", render: (row) => row.genre || "—" },
                  {
                    key: "status",
                    header: "状态",
                    render: (row) => <StatusBadge status={row.status as never} />,
                  },
                  {
                    key: "words",
                    header: "目标字数",
                    render: (row) => formatNumber(row.target_word_count),
                  },
                  {
                    key: "action",
                    header: "操作",
                    render: (row) => (
                      <Link href={`/studio/projects/${row.id}/write`}>
                        <Button variant="secondary" size="sm">
                          继续写作
                        </Button>
                      </Link>
                    ),
                  },
                ]}
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>生成任务</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {jobs.slice(0, 3).map((job) => (
              <div key={job.id} className="rounded-2xl border border-slate-200 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-bold text-slate-950">{job.job_type}</p>
                    <p className="mt-1 text-xs text-slate-500">
                      Workflow：{job.workflow_id ?? "未启动"}
                    </p>
                  </div>
                  <StatusBadge status={job.status as never} />
                </div>
                <ProgressBar
                  value={job.consumed_quota > 0 ? (job.consumed_quota / Math.max(job.reserved_quota, 1)) * 100 : 0}
                  className="mt-3"
                  tone={job.status === "failed" ? "orange" : "indigo"}
                />
                <p className="mt-2 text-xs text-slate-500">
                  预留 {job.reserved_quota.toLocaleString()} · 已结算{" "}
                  {job.consumed_quota.toLocaleString()}
                </p>
              </div>
            ))}
            {jobs.length === 0 ? (
              <p className="text-center text-sm text-slate-500">暂无任务</p>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <ActionCard title="创建小说项目" description="从空白开始创建新的小说项目" href="/studio/projects/new" icon={Plus} tone="violet" />
        <ActionCard title="生成故事圣经" description="AI 帮你构建世界观与设定" href="/studio/projects/demo-project/bible" icon={BookOpen} tone="blue" />
        <ActionCard title="生成第一章" description="快速生成小说开篇内容" href="/studio/projects/demo-project/write" icon={PenLine} tone="green" />
        <ActionCard title="查看额度" description="查看套餐额度与使用情况" href="/studio/usage" icon={Gauge} tone="orange" />
      </div>
    </div>
  );
}
