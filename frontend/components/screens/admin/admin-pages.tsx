"use client";

import { useQuery } from "@tanstack/react-query";
import { Area, AreaChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, Building2, LockKeyhole, Save, Sparkles, Users } from "lucide-react";
import { toast } from "sonner";
import { useState } from "react";

import { useAuth } from "@/components/providers/auth-provider";
import { Badge, PlanBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { ProgressBar, QuotaProgress } from "@/components/ui/progress";
import { StatCard } from "@/components/ui/stat-card";
import { adminApi, billingApi, jobsApi, quotaApi } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { isSuperAdmin } from "@/lib/permissions";

// 后端 admin/* 返回为 unknown[]，这里就近声明运行时形状
type AdminUser = {
  id: string;
  email: string;
  display_name: string;
  platform_role: string;
  status: string;
};

type AdminOrg = {
  id: string;
  name: string;
  type: string;
  plan_code: string;
  status: string;
  owner_user_id: string;
};

type AdminJob = {
  id: string;
  organization_id: string;
  project_id: string;
  job_type: string;
  status: string;
  priority: string;
  workflow_id: string | null;
  reserved_quota: number;
  consumed_quota: number;
};

type AdminModelCall = {
  id: string;
  organization_id: string;
  project_id: string | null;
  job_id: string | null;
  task_type: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  status: string;
  created_at: string;
};

type AdminAuditLog = {
  id: string;
  organization_id: string;
  actor_user_id: string;
  action: string;
  target_type: string;
  target_id: string;
  created_at: string;
};

type AdminContentReview = {
  id: string;
  organization_id: string;
  project_id: string;
  issue_type: string;
  severity: string;
  description: string;
  status: string;
  created_at: string;
};

export function AdminDashboardPage() {
  const { data: jobs = [] } = useQuery({
    queryKey: ["admin", "jobs"],
    queryFn: () => adminApi.jobs() as Promise<AdminJob[]>,
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

function AdminTitle({ title, desc }: { title: string; desc: string }) {
  return (
    <div>
      <h1 className="text-3xl font-black text-slate-950">{title}</h1>
      <p className="mt-1 text-slate-500">{desc}</p>
    </div>
  );
}

function AlertItem({
  tone,
  title,
  text,
}: {
  tone: "rose" | "amber" | "green";
  title: string;
  text: string;
}) {
  const color =
    tone === "rose"
      ? "bg-rose-50 text-rose-700"
      : tone === "amber"
      ? "bg-amber-50 text-amber-700"
      : "bg-emerald-50 text-emerald-700";
  return (
    <div className={`rounded-2xl p-4 ${color}`}>
      <p className="font-bold">{title}</p>
      <p className="mt-1 text-sm opacity-80">{text}</p>
    </div>
  );
}

export function AdminUsersPage() {
  const { data = [], isPending } = useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => adminApi.users() as Promise<AdminUser[]>,
  });
  return (
    <div className="space-y-6">
      <AdminTitle title="用户管理" desc="平台用户、角色、状态。" />
      {isPending ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">加载中…</CardContent>
        </Card>
      ) : (
        <DataTable
          rows={data}
          columns={[
            {
              key: "name",
              header: "用户",
              render: (row) => (
                <div>
                  <p className="font-bold text-slate-950">{row.display_name}</p>
                  <p className="text-xs text-slate-500">{row.email}</p>
                </div>
              ),
            },
            {
              key: "role",
              header: "角色",
              render: (row) => (
                <Badge tone={row.platform_role === "super_admin" ? "amber" : "blue"}>
                  {row.platform_role}
                </Badge>
              ),
            },
            {
              key: "status",
              header: "状态",
              render: (row) => (
                <StatusBadge status={row.status === "active" ? "succeeded" : "failed"} />
              ),
            },
            { key: "id", header: "user_id", render: (row) => row.id },
          ]}
        />
      )}
    </div>
  );
}

export function AdminOrganizationsPage() {
  const { data = [] } = useQuery({
    queryKey: ["admin", "organizations"],
    queryFn: () => adminApi.organizations() as Promise<AdminOrg[]>,
  });
  return (
    <div className="space-y-6">
      <AdminTitle title="组织管理" desc="组织状态、套餐、成员入口。" />
      {data.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">暂无组织。</CardContent>
        </Card>
      ) : (
        <DataTable
          rows={data}
          columns={[
            {
              key: "name",
              header: "组织",
              render: (row) => <span className="font-bold text-slate-950">{row.name}</span>,
            },
            { key: "owner", header: "owner_user_id", render: (row) => row.owner_user_id },
            {
              key: "plan",
              header: "Plan",
              render: (row) => <PlanBadge plan={row.plan_code as never} />,
            },
            {
              key: "status",
              header: "状态",
              render: (row) => (
                <StatusBadge
                  status={row.status === "active" ? "succeeded" : row.status === "trialing" ? "queued" : "failed"}
                />
              ),
            },
          ]}
        />
      )}
    </div>
  );
}

export function AdminPlansPage() {
  const { data = [] } = useQuery({
    queryKey: ["billing", "plans"],
    queryFn: () => billingApi.plans(),
  });
  return (
    <div className="space-y-6">
      <AdminTitle title="套餐 / 权益管理" desc="Plan、Feature、Entitlement 配置。" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        {data.map((plan) => (
          <Card key={plan.code}>
            <CardContent>
              <PlanBadge plan={plan.code as never} />
              <h3 className="mt-3 text-xl font-black text-slate-950">{plan.name}</h3>
              <p className="mt-2 min-h-12 text-sm text-slate-500">{plan.description}</p>
              <p className="mt-3 text-sm font-semibold text-slate-600">
                ¥{plan.price_monthly}/月 · {plan.status}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

export function AdminQuotasPage() {
  const { data = [] } = useQuery({
    queryKey: ["admin", "quotas"],
    queryFn: () => quotaApi.list(),
  });
  return (
    <div className="space-y-6">
      <AdminTitle title="额度管理" desc="组织额度、预留额度。手动调整接口需写入 audit_logs。" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {data.map((quota) => (
          <Card key={quota.id}>
            <CardContent>
              <div className="mb-3 flex items-center justify-between">
                <p className="font-bold text-slate-950">{quota.quota_key}</p>
                <Badge tone="blue">{quota.organization_id.slice(0, 10)}</Badge>
              </div>
              <QuotaProgress
                used={quota.used_value}
                reserved={quota.reserved_value}
                limit={quota.limit_value}
              />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

export function AdminGenerationJobsPage() {
  const { data = [], refetch } = useQuery({
    queryKey: ["admin", "jobs"],
    queryFn: () => adminApi.jobs() as Promise<AdminJob[]>,
  });

  const cancel = async (id: string) => {
    try {
      await jobsApi.cancel(id);
      toast.success("已取消，将写入 audit_logs");
      await refetch();
    } catch {
      toast.error("取消失败");
    }
  };

  return (
    <div className="space-y-6">
      <AdminTitle title="平台生成队列" desc="generation_jobs，支持强制取消。" />
      <Card>
        <CardHeader>
          <CardTitle>generation_jobs</CardTitle>
        </CardHeader>
        <CardContent>
          {data.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">暂无任务。</p>
          ) : (
            <AdminJobsTable rows={data} onCancel={cancel} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function AdminJobsTable({
  rows,
  onCancel,
}: {
  rows: AdminJob[];
  onCancel?: (id: string) => void;
}) {
  return (
    <DataTable
      rows={rows}
      columns={[
        {
          key: "title",
          header: "任务",
          render: (row) => (
            <div>
              <p className="font-bold text-slate-950">{row.job_type}</p>
              <p className="text-xs text-slate-500">{row.workflow_id ?? "未启动 workflow"}</p>
            </div>
          ),
        },
        { key: "org", header: "organization_id", render: (row) => row.organization_id },
        { key: "type", header: "task_type", render: (row) => row.job_type },
        {
          key: "status",
          header: "状态",
          render: (row) => <StatusBadge status={row.status as never} />,
        },
        {
          key: "quota",
          header: "额度",
          render: (row) => `${row.consumed_quota}/${row.reserved_quota}`,
        },
        {
          key: "progress",
          header: "进度",
          render: (row) => (
            <ProgressBar value={(row.consumed_quota / Math.max(row.reserved_quota, 1)) * 100} />
          ),
        },
        {
          key: "action",
          header: "强制操作",
          render: (row) =>
            onCancel ? (
              <Button size="sm" variant="danger" onClick={() => onCancel(row.id)}>
                取消
              </Button>
            ) : null,
        },
      ]}
    />
  );
}

export function AdminModelCallsPage() {
  const { data = [] } = useQuery({
    queryKey: ["admin", "model-calls"],
    queryFn: () => adminApi.modelCalls() as Promise<AdminModelCall[]>,
  });
  return (
    <div className="space-y-6">
      <AdminTitle title="模型调用日志" desc="ModelGateway 统一记录 task_type、model、token、latency、status。" />
      {data.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">暂无调用记录。</CardContent>
        </Card>
      ) : (
        <DataTable
          rows={data}
          columns={[
            { key: "task", header: "task_type", render: (row) => row.task_type },
            { key: "model", header: "model", render: (row) => row.model },
            {
              key: "tokens",
              header: "tokens",
              render: (row) => `in ${row.input_tokens} / out ${row.output_tokens}`,
            },
            { key: "latency", header: "latency", render: (row) => `${row.latency_ms}ms` },
            {
              key: "status",
              header: "status",
              render: (row) => (
                <StatusBadge status={row.status === "success" ? "succeeded" : "failed"} />
              ),
            },
            { key: "time", header: "时间", render: (row) => formatDateTime(row.created_at) },
          ]}
        />
      )}
    </div>
  );
}

export function AdminContentReviewPage() {
  const { data = [] } = useQuery({
    queryKey: ["admin", "content-reviews"],
    queryFn: () => adminApi.contentReviews() as Promise<AdminContentReview[]>,
  });
  return (
    <div className="space-y-6">
      <AdminTitle title="内容审核 / 风控" desc="待审核内容、风险等级、处理动作。" />
      {data.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">暂无需要审核的内容。</CardContent>
        </Card>
      ) : (
        <DataTable
          rows={data}
          columns={[
            {
              key: "title",
              header: "内容",
              render: (row) => (
                <div>
                  <p className="font-bold text-slate-950">{row.description.slice(0, 60)}</p>
                  <p className="text-xs text-slate-500">
                    {row.organization_id} / {row.project_id}
                  </p>
                </div>
              ),
            },
            { key: "type", header: "类型", render: (row) => row.issue_type },
            {
              key: "severity",
              header: "风险",
              render: (row) => (
                <Badge
                  tone={
                    row.severity === "high"
                      ? "rose"
                      : row.severity === "medium"
                      ? "amber"
                      : "green"
                  }
                >
                  {row.severity}
                </Badge>
              ),
            },
            { key: "status", header: "状态", render: (row) => row.status },
            { key: "time", header: "时间", render: (row) => formatDateTime(row.created_at) },
          ]}
        />
      )}
    </div>
  );
}

export function AdminSettingsPage() {
  const { user } = useAuth();
  const editable = isSuperAdmin(user);
  const [model, setModel] = useState("gpt-4o");
  return (
    <div className="space-y-6">
      <AdminTitle title="系统设置" desc="模型配置、Prompt 版本、队列；仅 super_admin 可修改。" />
      {!editable ? (
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="flex items-center gap-3 text-amber-800">
            <LockKeyhole className="size-5" /> 当前角色只能查看。
          </CardContent>
        </Card>
      ) : null}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>模型配置</CardTitle>
          <Badge tone={editable ? "green" : "amber"}>
            {editable ? "super_admin 可编辑" : "只读"}
          </Badge>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <label className="block text-sm font-bold text-slate-700">
            默认文本模型
            <input
              disabled={!editable}
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-4 disabled:bg-slate-100"
            />
          </label>
          <Button
            disabled={!editable}
            onClick={() => toast.info("系统设置写入接口待对接")}
          >
            <Save className="size-4" /> 保存
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

export function AdminAuditLogsPage() {
  const { data = [] } = useQuery({
    queryKey: ["admin", "audit-logs"],
    queryFn: () => adminApi.auditLogs() as Promise<AdminAuditLog[]>,
  });
  return (
    <div className="space-y-6">
      <AdminTitle title="审计日志" desc="所有管理员破坏性操作必须记录。" />
      {data.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">暂无审计日志。</CardContent>
        </Card>
      ) : (
        <DataTable
          rows={data}
          columns={[
            {
              key: "actor",
              header: "actor",
              render: (row) => <span className="font-bold text-slate-950">{row.actor_user_id}</span>,
            },
            { key: "action", header: "action", render: (row) => row.action },
            { key: "target", header: "target", render: (row) => `${row.target_type}/${row.target_id}` },
            { key: "org", header: "组织", render: (row) => row.organization_id },
            { key: "time", header: "时间", render: (row) => formatDateTime(row.created_at) },
          ]}
        />
      )}
    </div>
  );
}
