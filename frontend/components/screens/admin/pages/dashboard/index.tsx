"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Building2, Sparkles, Users } from "lucide-react";
import { Area, AreaChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";

import { AdminTitle } from "@/components/ui/admin-title";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import { AdminJobsTable } from "@/components/screens/admin/shared/admin-jobs-table";
import type { AdminOrg } from "@/components/screens/admin/shared/types";
import { adminApi, type AdminUser, type GenerationJob } from "@/lib/api";

import { AlertItem } from "./alert-item";

export function AdminDashboardPage() {
  const { data: jobs = [] } = useQuery({
    queryKey: ["admin", "jobs"],
    queryFn: () => adminApi.jobs() as Promise<GenerationJob[]>,
  });
  const { data: users = [] } = useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => adminApi.users() as Promise<AdminUser[]>,
  });
  const { data: orgs = [] } = useQuery({
    queryKey: ["admin", "organizations"],
    queryFn: () => adminApi.organizations() as Promise<AdminOrg[]>,
  });

  const failedJobs = jobs.filter((j) => j.status === "failed").length;
  const runningJobs = jobs.filter((j) => j.status === "running").length;

  return (
    <div className="space-y-6">
      <AdminTitle title="Admin 后台总览" desc="平台级运营数据、任务队列、系统状态和告警。" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="注册用户" value={String(users.length)} icon={Users} tone="blue" />
        <StatCard label="组织数" value={String(orgs.length)} icon={Building2} tone="green" />
        <StatCard label="运行中任务" value={String(runningJobs)} icon={Sparkles} tone="violet" />
        <StatCard
          label="失败任务"
          value={String(failedJobs)}
          delta={failedJobs ? "需关注" : ""}
          icon={AlertTriangle}
          tone="orange"
        />
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <CardHeader>
            <CardTitle>最近任务趋势（占位）</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <AreaChart width={720} height={260} data={[]}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" />
              <YAxis />
              <Tooltip />
              <Area type="monotone" dataKey="value" stroke="#6366f1" fill="#6366f155" />
            </AreaChart>
            <p className="text-center text-xs text-slate-400">趋势接口待补；当前展示空图。</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>系统状态</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <AlertItem tone="green" title="API 服务" text="可达。建议同时巡检 /healthz/ready。" />
            <AlertItem tone="amber" title="Temporal worker" text="生产环境请确保 worker 已注册。" />
            <AlertItem tone="rose" title="模型调用" text="如启用真实 provider，请监控错误率。" />
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>最新生成任务</CardTitle>
        </CardHeader>
        <CardContent>
          {jobs.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">暂无任务。</p>
          ) : (
            <AdminJobsTable rows={jobs} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
