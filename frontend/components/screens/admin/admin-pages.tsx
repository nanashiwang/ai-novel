"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Area, AreaChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  EyeOff,
  KeyRound,
  Link2,
  LockKeyhole,
  Plus,
  Save,
  Server,
  Sparkles,
  Trash2,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import { useState } from "react";

import { useAuth } from "@/components/providers/auth-provider";
import { Badge, PlanBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { QuotaProgress } from "@/components/ui/progress";
import { StatCard } from "@/components/ui/stat-card";
import {
  adminApi,
  type AdminPlan,
  type AdminPlanFeature,
  type AdminPlanUpsert,
  type AdminUser,
  type AdminUserUpdate,
  type GenerationJob,
  type ModelGatewaySettingsUpdate,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { isSuperAdmin } from "@/lib/permissions";
import { AdminTitle } from "@/components/ui/admin-title";
import { AdminJobsTable } from "@/components/screens/admin/shared/admin-jobs-table";

// 后端 admin/* 返回为 unknown[]，这里就近声明运行时形状
type AdminOrg = {
  id: string;
  name: string;
  type: string;
  plan_code: string;
  status: string;
  owner_user_id: string;
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
  const queryClient = useQueryClient();
  const { user: currentUser } = useAuth();
  const isSuper = isSuperAdmin(currentUser);
  const { data = [], isPending } = useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => adminApi.users() as Promise<AdminUser[]>,
  });
  const [detailUserId, setDetailUserId] = useState<string | null>(null);

  const updateMutation = useMutation({
    mutationFn: ({ userId, payload }: { userId: string; payload: AdminUserUpdate }) =>
      adminApi.updateUser(userId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "audit-logs"] });
      if (detailUserId) {
        queryClient.invalidateQueries({ queryKey: ["admin", "user", detailUserId] });
      }
      toast.success("已保存");
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : "保存失败"),
  });
  const resetPwdMutation = useMutation({
    mutationFn: (userId: string) => adminApi.resetUserPassword(userId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["admin", "audit-logs"] });
      window.prompt(
        "已重置密码。请复制临时密码并通过安全渠道告知用户：",
        data.temp_password,
      );
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : "重置失败"),
  });

  function toggleStatus(row: AdminUser) {
    if (row.id === currentUser?.id) {
      toast.error("不能禁用自己");
      return;
    }
    const nextStatus = row.status === "active" ? "disabled" : "active";
    if (!window.confirm(`确认把 ${row.email} 设为 ${nextStatus}？`)) return;
    updateMutation.mutate({ userId: row.id, payload: { status: nextStatus } });
  }

  function changeRole(row: AdminUser, nextRole: string) {
    if (nextRole === row.platform_role) return;
    if (row.id === currentUser?.id) {
      toast.error("不能修改自己的角色");
      return;
    }
    if ((nextRole === "admin" || nextRole === "super_admin") && !isSuper) {
      toast.error("仅 super_admin 可提升角色");
      return;
    }
    if (!window.confirm(`确认把 ${row.email} 的角色改为 ${nextRole}？`)) return;
    updateMutation.mutate({ userId: row.id, payload: { platform_role: nextRole } });
  }

  function resetPwd(row: AdminUser) {
    if (!window.confirm(`确认重置 ${row.email} 的密码？旧密码将立即失效。`)) return;
    resetPwdMutation.mutate(row.id);
  }

  return (
    <div className="space-y-6">
      <AdminTitle title="用户管理" desc="平台用户、角色、状态。可禁用、改角色、重置密码。" />
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
                  <button
                    type="button"
                    onClick={() => setDetailUserId(row.id)}
                    className="text-left font-bold text-slate-950 hover:text-indigo-600"
                  >
                    {row.display_name}
                  </button>
                  <p className="text-xs text-slate-500">{row.email}</p>
                </div>
              ),
            },
            {
              key: "role",
              header: "角色",
              render: (row) => (
                <select
                  disabled={row.id === currentUser?.id}
                  value={row.platform_role}
                  onChange={(e) => changeRole(row, e.target.value)}
                  className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs disabled:bg-slate-100"
                >
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                  <option value="super_admin">super_admin</option>
                </select>
              ),
            },
            {
              key: "status",
              header: "状态",
              render: (row) => (
                <StatusBadge status={row.status === "active" ? "succeeded" : "failed"} />
              ),
            },
            {
              key: "actions",
              header: "操作",
              render: (row) => (
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={row.id === currentUser?.id || updateMutation.isPending}
                    onClick={() => toggleStatus(row)}
                  >
                    {row.status === "active" ? "禁用" : "启用"}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={resetPwdMutation.isPending}
                    onClick={() => resetPwd(row)}
                  >
                    <KeyRound className="size-3.5" /> 重置密码
                  </Button>
                </div>
              ),
            },
            { key: "id", header: "user_id", render: (row) => row.id },
          ]}
        />
      )}
      {detailUserId ? (
        <UserDetailDrawer userId={detailUserId} onClose={() => setDetailUserId(null)} />
      ) : null}
    </div>
  );
}

function UserDetailDrawer({
  userId,
  onClose,
}: {
  userId: string;
  onClose: () => void;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "user", userId],
    queryFn: () => adminApi.user(userId),
  });
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>用户详情</CardTitle>
        <Button size="sm" variant="ghost" onClick={onClose}>
          关闭
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading || !data ? (
          <p className="text-sm text-slate-500">加载中…</p>
        ) : (
          <>
            <div className="space-y-1 text-sm">
              <p className="font-bold text-slate-950">{data.display_name}</p>
              <p className="text-slate-500">{data.email}</p>
              <p className="text-xs text-slate-400">user_id: {data.id}</p>
            </div>
            <div>
              <p className="mb-2 text-sm font-bold text-slate-700">所属组织</p>
              {data.organizations.length === 0 ? (
                <p className="text-sm text-slate-500">未加入任何组织。</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {data.organizations.map((org) => (
                    <li
                      key={org.organization_id}
                      className="flex items-center justify-between rounded-lg border border-slate-200 p-3"
                    >
                      <div>
                        <p className="font-semibold text-slate-900">{org.organization_name}</p>
                        <p className="text-xs text-slate-500">{org.organization_id}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge tone="blue">{org.role}</Badge>
                        <PlanBadge plan={org.plan_code as never} />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export function AdminOrganizationsPage() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const editable = isSuperAdmin(user);
  const { data = [] } = useQuery({
    queryKey: ["admin", "organizations"],
    queryFn: () => adminApi.organizations() as Promise<AdminOrg[]>,
  });
  const { data: plans = [] } = useQuery({
    queryKey: ["admin", "plans"],
    queryFn: adminApi.plans,
  });
  // 仅 active 套餐可用于切换；archived 仍允许保留历史绑定
  const activePlanCodes = plans
    .filter((p) => p.status === "active")
    .map((p) => p.code);

  const switchPlanMutation = useMutation({
    mutationFn: ({ orgId, planCode }: { orgId: string; planCode: string }) =>
      adminApi.updateOrganization(orgId, {
        plan_code: planCode,
        reason: "admin 手动调整",
      }),
    onSuccess: () => {
      toast.success("已切换套餐，额度按新套餐自动同步");
      queryClient.invalidateQueries({ queryKey: ["admin", "organizations"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "plans"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "quotas"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "audit-logs"] });
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "切换套餐失败");
    },
  });

  function changePlan(row: AdminOrg, nextPlan: string) {
    if (nextPlan === row.plan_code) return;
    const confirmed = window.confirm(
      `确认把组织 ${row.name} 从 ${row.plan_code} 切换为 ${nextPlan}？\n` +
        `已用额度（used）保留，额度上限会按新套餐重置。`,
    );
    if (!confirmed) return;
    switchPlanMutation.mutate({ orgId: row.id, planCode: nextPlan });
  }

  return (
    <div className="space-y-6">
      <AdminTitle title="组织管理" desc="组织状态、套餐、成员入口。" />
      {!editable ? (
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="flex items-center gap-3 text-amber-800">
            <LockKeyhole className="size-5" /> 仅 super_admin 可切换套餐。
          </CardContent>
        </Card>
      ) : null}
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
              render: (row) => (
                <div className="flex items-center gap-2">
                  <PlanBadge plan={row.plan_code as never} />
                  <select
                    disabled={!editable || switchPlanMutation.isPending}
                    value={row.plan_code}
                    onChange={(e) => changePlan(row, e.target.value)}
                    className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs disabled:bg-slate-100"
                  >
                    {!activePlanCodes.includes(row.plan_code) ? (
                      <option value={row.plan_code}>{row.plan_code}（当前）</option>
                    ) : null}
                    {activePlanCodes.map((code) => (
                      <option key={code} value={code}>
                        {code}
                      </option>
                    ))}
                  </select>
                </div>
              ),
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
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const editable = isSuperAdmin(user);
  const { data = [], isLoading } = useQuery({
    queryKey: ["admin", "plans"],
    queryFn: adminApi.plans,
  });
  const { data: quotaKeyOptions = [] } = useQuery({
    queryKey: ["admin", "quota-keys"],
    queryFn: adminApi.quotaKeys,
  });
  const [selectedId, setSelectedId] = useState<string | "new">("new");
  const selectedPlan =
    selectedId === "new" ? undefined : data.find((plan) => plan.id === selectedId);
  const [draft, setDraft] = useState<Partial<AdminPlanUpsert>>({});
  const form = buildPlanForm(selectedPlan, draft);

  const saveMutation = useMutation({
    mutationFn: (payload: AdminPlanUpsert) =>
      selectedPlan
        ? adminApi.updatePlan(selectedPlan.id, payload)
        : adminApi.createPlan(payload),
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ["admin", "plans"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "quota-keys"] });
      queryClient.invalidateQueries({ queryKey: ["billing", "plans"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "audit-logs"] });
      setSelectedId(saved.id);
      setDraft({});
      toast.success("套餐已保存");
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "保存失败");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (planId: string) => adminApi.deletePlan(planId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "plans"] });
      queryClient.invalidateQueries({ queryKey: ["billing", "plans"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "audit-logs"] });
      setSelectedId("new");
      setDraft({});
      toast.success("套餐已删除");
    },
    onError: (error) => {
      const msg = error instanceof Error ? error.message : "删除失败";
      // 后端返回 plan_in_use 时给更友好的提示
      toast.error(msg.includes("plan_in_use") ? "仍有组织使用此套餐，无法删除" : msg);
    },
  });

  function selectPlan(id: string | "new") {
    setSelectedId(id);
    setDraft({});
  }

  function updateField<K extends keyof AdminPlanUpsert>(key: K, value: AdminPlanUpsert[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function updateFeature(index: number, patch: Partial<AdminPlanFeature>) {
    const features = form.features.map((feature, featureIndex) =>
      featureIndex === index ? { ...feature, ...patch } : feature,
    );
    updateField("features", features);
  }

  function addFeature() {
    updateField("features", [
      ...form.features,
      {
        feature_key: quotaKeyOptions[0]?.feature_key ?? "monthly_generated_words",
        enabled: true,
        limit_value: 0,
        limit_unit: "words",
      },
    ]);
  }

  function removeFeature(index: number) {
    updateField(
      "features",
      form.features.filter((_, featureIndex) => featureIndex !== index),
    );
  }

  function deletePlan() {
    if (!selectedPlan) return;
    const orgCount = selectedPlan.organization_count ?? 0;
    if (orgCount > 0) {
      toast.error(`仍有 ${orgCount} 个组织在使用此套餐，请先把它们迁走再删除`);
      return;
    }
    if (!window.confirm(`确认删除套餐「${selectedPlan.name}」？此操作不可恢复。`)) return;
    deleteMutation.mutate(selectedPlan.id);
  }

  function savePlan() {
    const payload: AdminPlanUpsert = {
      ...form,
      code: form.code.trim(),
      name: form.name.trim(),
      description: form.description.trim(),
      currency: form.currency.trim() || "CNY",
      status: form.status.trim() || "active",
      price_monthly: Number(form.price_monthly) || 0,
      price_yearly: form.price_yearly === null ? null : Number(form.price_yearly) || 0,
      features: form.features
        .filter((feature) => feature.feature_key.trim())
        .map((feature) => ({
          feature_key: feature.feature_key.trim(),
          enabled: feature.enabled,
          limit_value:
            feature.limit_value === null || Number.isNaN(Number(feature.limit_value))
              ? null
              : Number(feature.limit_value),
          limit_unit: feature.limit_unit.trim() || "times",
        })),
    };
    saveMutation.mutate(payload);
  }

  const canSave = editable && form.code.trim() && form.name.trim();

  return (
    <div className="space-y-6">
      <AdminTitle title="套餐 / 权益管理" desc="自定义套餐、价格周期和周期内额度。" />
      {!editable ? (
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="flex items-center gap-3 text-amber-800">
            <LockKeyhole className="size-5" /> 当前角色只能查看。
          </CardContent>
        </Card>
      ) : null}
      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>套餐列表</CardTitle>
            <Button size="sm" variant="secondary" disabled={!editable} onClick={() => selectPlan("new")}>
              <Plus className="size-4" /> 新增
            </Button>
          </CardHeader>
          <CardContent className="space-y-2">
            {isLoading ? (
              <p className="py-8 text-center text-sm text-slate-500">加载中…</p>
            ) : data.length === 0 ? (
              <p className="py-8 text-center text-sm text-slate-500">暂无套餐。</p>
            ) : (
              data.map((plan) => (
                <button
                  key={plan.id}
                  type="button"
                  onClick={() => selectPlan(plan.id)}
                  className={`w-full rounded-xl border p-4 text-left transition ${
                    selectedId === plan.id
                      ? "border-indigo-500 bg-indigo-50"
                      : "border-slate-200 bg-white hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <PlanBadge plan={plan.code as never} />
                    <StatusBadge status={plan.status === "active" ? "succeeded" : "queued"} />
                  </div>
                  <p className="mt-3 font-black text-slate-950">{plan.name}</p>
                  <p className="mt-1 truncate text-sm text-slate-500">{plan.description || "-"}</p>
                  <p className="mt-2 text-sm font-semibold text-slate-700">
                    {plan.currency} {plan.price_monthly}/月
                    {plan.price_yearly !== null ? ` · ${plan.price_yearly}/年` : ""}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    <Building2 className="mr-1 inline size-3" />
                    使用组织：{plan.organization_count ?? 0}
                  </p>
                </button>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-4">
            <div>
              <CardTitle>{selectedPlan ? "编辑套餐" : "新增套餐"}</CardTitle>
              <p className="mt-1 text-sm text-slate-500">
                额度项会用于生成任务的周期限制。
              </p>
            </div>
            <div className="flex items-center gap-2">
              {selectedPlan ? (
                <Badge tone={(selectedPlan.organization_count ?? 0) > 0 ? "blue" : "amber"}>
                  绑定组织 {selectedPlan.organization_count ?? 0}
                </Badge>
              ) : null}
              <Badge tone={editable ? "green" : "amber"}>
                {editable ? "super_admin 可编辑" : "只读"}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2">
              <label className="block text-sm font-bold text-slate-700">
                套餐编码
                <input
                  disabled={!editable}
                  value={form.code}
                  onChange={(e) => updateField("code", e.target.value)}
                  placeholder="Pro"
                  className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-4 disabled:bg-slate-100"
                />
              </label>
              <label className="block text-sm font-bold text-slate-700">
                套餐名称
                <input
                  disabled={!editable}
                  value={form.name}
                  onChange={(e) => updateField("name", e.target.value)}
                  placeholder="Pro"
                  className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-4 disabled:bg-slate-100"
                />
              </label>
              <label className="block text-sm font-bold text-slate-700 md:col-span-2">
                描述
                <input
                  disabled={!editable}
                  value={form.description}
                  onChange={(e) => updateField("description", e.target.value)}
                  placeholder="长篇小说自动生产与审稿"
                  className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-4 disabled:bg-slate-100"
                />
              </label>
            </div>

            <div className="grid gap-4 md:grid-cols-4">
              <label className="block text-sm font-bold text-slate-700">
                月付价格
                <input
                  disabled={!editable}
                  value={form.price_monthly}
                  onChange={(e) => updateField("price_monthly", Number(e.target.value))}
                  type="number"
                  min="0"
                  className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-4 disabled:bg-slate-100"
                />
              </label>
              <label className="block text-sm font-bold text-slate-700">
                年付价格
                <input
                  disabled={!editable}
                  value={form.price_yearly ?? ""}
                  onChange={(e) =>
                    updateField(
                      "price_yearly",
                      e.target.value === "" ? null : Number(e.target.value),
                    )
                  }
                  type="number"
                  min="0"
                  placeholder="可留空"
                  className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-4 disabled:bg-slate-100"
                />
              </label>
              <label className="block text-sm font-bold text-slate-700">
                币种
                <input
                  disabled={!editable}
                  value={form.currency}
                  onChange={(e) => updateField("currency", e.target.value)}
                  className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-4 disabled:bg-slate-100"
                />
              </label>
              <label className="block text-sm font-bold text-slate-700">
                状态
                <select
                  disabled={!editable}
                  value={form.status}
                  onChange={(e) => updateField("status", e.target.value)}
                  className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-4 disabled:bg-slate-100"
                >
                  <option value="active">active</option>
                  <option value="draft">draft</option>
                  <option value="archived">archived</option>
                </select>
              </label>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-bold text-slate-950">周期内额度</p>
                  <p className="text-sm text-slate-500">
                    例如每月生成字数、审核次数、重写次数。
                  </p>
                </div>
                <Button size="sm" variant="secondary" disabled={!editable} onClick={addFeature}>
                  <Plus className="size-4" /> 添加额度
                </Button>
              </div>

              <div className="space-y-3">
                {form.features.map((feature, index) => (
                  <div
                    key={`${feature.feature_key}-${index}`}
                    className="grid gap-3 rounded-xl border border-slate-200 p-3 md:grid-cols-[1fr_140px_120px_90px_40px]"
                  >
                    <input
                      disabled={!editable}
                      value={feature.feature_key}
                      onChange={(e) => updateFeature(index, { feature_key: e.target.value })}
                      placeholder="monthly_generated_words"
                      list="admin-plan-quota-keys"
                      className="h-10 rounded-xl border border-slate-200 px-3 disabled:bg-slate-100"
                    />
                    <input
                      disabled={!editable}
                      value={feature.limit_value ?? ""}
                      onChange={(e) =>
                        updateFeature(index, {
                          limit_value: e.target.value === "" ? null : Number(e.target.value),
                        })
                      }
                      type="number"
                      min="0"
                      placeholder="额度"
                      className="h-10 rounded-xl border border-slate-200 px-3 disabled:bg-slate-100"
                    />
                    <input
                      disabled={!editable}
                      value={feature.limit_unit}
                      onChange={(e) => updateFeature(index, { limit_unit: e.target.value })}
                      placeholder="words"
                      className="h-10 rounded-xl border border-slate-200 px-3 disabled:bg-slate-100"
                    />
                    <label className="flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-3 text-sm font-semibold text-slate-700">
                      <input
                        disabled={!editable}
                        checked={feature.enabled}
                        onChange={(e) => updateFeature(index, { enabled: e.target.checked })}
                        type="checkbox"
                      />
                      启用
                    </label>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={!editable}
                      onClick={() => removeFeature(index)}
                      className="h-10 px-0"
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                ))}
                {form.features.length === 0 ? (
                  <p className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
                    暂无额度项。
                  </p>
                ) : null}
                {/* 全局 datalist：feature_key 自动补全。来源 GET /admin/quota-keys */}
                <datalist id="admin-plan-quota-keys">
                  {quotaKeyOptions.map((opt) => (
                    <option key={opt.feature_key} value={opt.feature_key}>
                      {opt.feature_key}
                    </option>
                  ))}
                </datalist>
              </div>
            </div>

            <div className="flex items-center justify-between border-t border-slate-100 pt-5">
              {selectedPlan ? (
                <Button
                  variant="ghost"
                  disabled={!editable || deleteMutation.isPending}
                  onClick={deletePlan}
                  className="text-red-600 hover:bg-red-50"
                >
                  <Trash2 className="size-4" />
                  {deleteMutation.isPending ? "删除中" : "删除套餐"}
                </Button>
              ) : (
                <span />
              )}
              <Button disabled={!canSave || saveMutation.isPending} onClick={savePlan}>
                <Save className="size-4" />
                {saveMutation.isPending ? "保存中" : "保存套餐"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function buildPlanForm(
  plan: AdminPlan | undefined,
  draft: Partial<AdminPlanUpsert>,
): AdminPlanUpsert {
  return {
    code: draft.code ?? plan?.code ?? "",
    name: draft.name ?? plan?.name ?? "",
    description: draft.description ?? plan?.description ?? "",
    price_monthly: draft.price_monthly ?? plan?.price_monthly ?? 0,
    price_yearly: draft.price_yearly ?? plan?.price_yearly ?? null,
    currency: draft.currency ?? plan?.currency ?? "CNY",
    status: draft.status ?? plan?.status ?? "active",
    features:
      draft.features ??
      plan?.features.map((feature) => ({
        feature_key: feature.feature_key,
        enabled: feature.enabled,
        limit_value: feature.limit_value,
        limit_unit: feature.limit_unit,
      })) ??
      [
        {
          feature_key: "monthly_generated_words",
          enabled: true,
          limit_value: 50000,
          limit_unit: "words",
        },
      ],
  };
}

export function AdminQuotasPage() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const editable = isSuperAdmin(user);
  const [filter, setFilter] = useState<{ organization_id: string; quota_key: string }>({
    organization_id: "",
    quota_key: "",
  });
  const queryFilter = {
    organization_id: filter.organization_id || undefined,
    quota_key: filter.quota_key || undefined,
  };
  const { data = [], isLoading } = useQuery({
    queryKey: ["admin", "quotas", queryFilter],
    queryFn: () => adminApi.quotaBalances(queryFilter),
  });
  const { data: quotaKeyOptions = [] } = useQuery({
    queryKey: ["admin", "quota-keys"],
    queryFn: adminApi.quotaKeys,
  });

  const adjustMutation = useMutation({
    mutationFn: ({
      orgId,
      payload,
    }: {
      orgId: string;
      payload: { quota_key: string; delta: number; reason: string };
    }) => adminApi.adjustOrganizationQuota(orgId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "quotas"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "audit-logs"] });
      toast.success("已写入 audit_logs");
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : "调整失败"),
  });

  function adjust(quota: { organization_id: string; quota_key: string }, sign: 1 | -1) {
    const raw = window.prompt(
      `输入要${sign > 0 ? "增加" : "扣减"}的额度（${quota.quota_key}）：`,
      "1000",
    );
    if (!raw) return;
    const amount = Number(raw);
    if (!Number.isFinite(amount) || amount <= 0) {
      toast.error("请输入正整数");
      return;
    }
    const reason = window.prompt("调整原因（写入 audit_log）", "运营补偿") || "";
    adjustMutation.mutate({
      orgId: quota.organization_id,
      payload: { quota_key: quota.quota_key, delta: sign * amount, reason },
    });
  }

  return (
    <div className="space-y-6">
      <AdminTitle title="额度管理" desc="组织额度 / 预留 / 已用。手动调整自动写入 audit_logs。" />
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center gap-3">
          <CardTitle>quota_balances</CardTitle>
          <input
            type="text"
            placeholder="organization_id 过滤"
            value={filter.organization_id}
            onChange={(e) =>
              setFilter((f) => ({ ...f, organization_id: e.target.value.trim() }))
            }
            className="h-9 w-64 rounded-lg border border-slate-200 px-3 text-sm"
          />
          <select
            value={filter.quota_key}
            onChange={(e) => setFilter((f) => ({ ...f, quota_key: e.target.value }))}
            className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm"
          >
            <option value="">全部额度类型</option>
            {quotaKeyOptions.map((opt) => (
              <option key={opt.feature_key} value={opt.feature_key}>
                {opt.feature_key}
              </option>
            ))}
          </select>
          {!editable ? (
            <Badge tone="amber">仅 super_admin 可调整</Badge>
          ) : null}
        </CardHeader>
      </Card>
      {isLoading ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">加载中…</CardContent>
        </Card>
      ) : data.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">
            暂无符合条件的额度记录。
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((quota) => (
            <Card key={quota.id}>
              <CardContent>
                <div className="mb-3 flex items-center justify-between">
                  <p className="font-bold text-slate-950">{quota.quota_key}</p>
                  <Badge tone="blue">{quota.organization_id.slice(0, 14)}</Badge>
                </div>
                <QuotaProgress
                  used={quota.used_value}
                  reserved={quota.reserved_value}
                  limit={quota.limit_value}
                />
                <div className="mt-3 flex justify-end gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={!editable || adjustMutation.isPending}
                    onClick={() => adjust(quota, 1)}
                  >
                    + 加额
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={!editable || adjustMutation.isPending}
                    onClick={() => adjust(quota, -1)}
                  >
                    − 扣减
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

export function AdminGenerationJobsPage() {
  const [filter, setFilter] = useState<{
    project_id: string;
    job_type: string;
    status: string;
  }>({ project_id: "", job_type: "", status: "" });

  const queryFilter = {
    project_id: filter.project_id || undefined,
    job_type: filter.job_type || undefined,
    status: filter.status || undefined,
  };

  const { data = [], refetch } = useQuery({
    queryKey: ["admin", "jobs", queryFilter],
    queryFn: () => adminApi.jobs(queryFilter) as Promise<GenerationJob[]>,
  });

  const cancel = async (id: string) => {
    try {
      await adminApi.cancelJob(id);
      toast.success("已取消，将写入 audit_logs");
      await refetch();
    } catch {
      toast.error("取消失败");
    }
  };

  return (
    <div className="space-y-6">
      <AdminTitle title="平台生成队列" desc="generation_jobs，支持按 project / type / status 过滤与强制取消。" />
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center gap-3">
          <CardTitle>generation_jobs</CardTitle>
          <input
            type="text"
            placeholder="project_id 过滤"
            value={filter.project_id}
            onChange={(e) => setFilter((f) => ({ ...f, project_id: e.target.value }))}
            className="h-9 w-56 rounded-lg border border-slate-200 px-3 text-sm"
          />
          <input
            type="text"
            placeholder="job_type 过滤"
            value={filter.job_type}
            onChange={(e) => setFilter((f) => ({ ...f, job_type: e.target.value }))}
            className="h-9 w-44 rounded-lg border border-slate-200 px-3 text-sm"
          />
          <select
            value={filter.status}
            onChange={(e) => setFilter((f) => ({ ...f, status: e.target.value }))}
            className="h-9 rounded-lg border border-slate-200 px-3 text-sm"
          >
            <option value="">全部状态</option>
            <option value="queued">queued</option>
            <option value="running">running</option>
            <option value="succeeded">succeeded</option>
            <option value="failed">failed</option>
            <option value="cancelled">cancelled</option>
          </select>
          <Button size="sm" variant="ghost" onClick={() => refetch()}>
            刷新
          </Button>
        </CardHeader>
        <CardContent>
          {data.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">无匹配任务。</p>
          ) : (
            <AdminJobsTable rows={data} onCancel={cancel} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function AdminModelCallsPage() {
  const [filter, setFilter] = useState<{ project_id: string; job_id: string }>(
    { project_id: "", job_id: "" },
  );
  const queryFilter = {
    project_id: filter.project_id || undefined,
    job_id: filter.job_id || undefined,
  };
  const { data = [], refetch } = useQuery({
    queryKey: ["admin", "model-calls", queryFilter],
    queryFn: () => adminApi.modelCalls(queryFilter) as Promise<AdminModelCall[]>,
  });
  return (
    <div className="space-y-6">
      <AdminTitle title="模型调用日志" desc="ModelGateway 统一记录 task_type、model、token、latency、status；可按 project / job drill-down。" />
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center gap-3">
          <CardTitle>model_calls</CardTitle>
          <input
            type="text"
            placeholder="project_id"
            value={filter.project_id}
            onChange={(e) => setFilter((f) => ({ ...f, project_id: e.target.value }))}
            className="h-9 w-56 rounded-lg border border-slate-200 px-3 text-sm"
          />
          <input
            type="text"
            placeholder="job_id"
            value={filter.job_id}
            onChange={(e) => setFilter((f) => ({ ...f, job_id: e.target.value }))}
            className="h-9 w-56 rounded-lg border border-slate-200 px-3 text-sm"
          />
          <Button size="sm" variant="ghost" onClick={() => refetch()}>
            刷新
          </Button>
        </CardHeader>
        <CardContent>
          {data.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">无匹配记录。</p>
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
                {
                  key: "job",
                  header: "job_id",
                  render: (row) =>
                    row.job_id ? (
                      <button
                        type="button"
                        className="font-mono text-xs text-indigo-600 hover:underline"
                        onClick={() =>
                          setFilter((f) => ({ ...f, job_id: row.job_id ?? "" }))
                        }
                        title="点击 drill-down 到该 job"
                      >
                        {row.job_id.slice(0, 16)}…
                      </button>
                    ) : (
                      <span className="text-slate-400">—</span>
                    ),
                },
                { key: "time", header: "时间", render: (row) => formatDateTime(row.created_at) },
              ]}
            />
          )}
        </CardContent>
      </Card>
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
  const queryClient = useQueryClient();
  const editable = isSuperAdmin(user);
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "settings", "model-gateway"],
    queryFn: adminApi.modelGatewaySettings,
  });
  const [draft, setDraft] = useState<Partial<ModelGatewaySettingsUpdate>>({});
  const form: ModelGatewaySettingsUpdate = {
    provider: draft.provider ?? data?.provider ?? "openai",
    default_model: draft.default_model ?? data?.default_model ?? "gpt-5.5",
    openai_base_url:
      draft.openai_base_url ?? data?.openai_base_url ?? "https://api.openai.com/v1",
    openai_api_key: draft.openai_api_key ?? "",
    anthropic_base_url:
      draft.anthropic_base_url ?? data?.anthropic_base_url ?? "https://api.anthropic.com/v1",
    anthropic_api_key: draft.anthropic_api_key ?? "",
  };

  const saveMutation = useMutation({
    mutationFn: (payload: ModelGatewaySettingsUpdate) =>
      adminApi.updateModelGatewaySettings(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "settings", "model-gateway"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "audit-logs"] });
      setDraft({});
      toast.success("模型配置已保存");
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "保存失败");
    },
  });

  const testMutation = useMutation({
    mutationFn: () => {
      // 只传当前 form 草稿里"非空"的字段。后端会把缺失字段回落到 db 里
      // 已存的值，从而支持"我只改 base_url，用现有 Key 测试"等场景。
      const payload: import("@/lib/api").ModelGatewayTestPayload = {
        provider: form.provider,
        default_model: form.default_model.trim() || undefined,
        openai_base_url: form.openai_base_url.trim() || undefined,
        openai_api_key: form.openai_api_key?.trim() || undefined,
        anthropic_base_url: form.anthropic_base_url.trim() || undefined,
        anthropic_api_key: form.anthropic_api_key?.trim() || undefined,
      };
      return adminApi.testModelGateway(payload);
    },
    onSuccess: (result) => {
      if (result.ok) {
        toast.success(
          `连接成功（${result.latency_ms} ms）样例：${result.sample || "OK"}`,
        );
      } else {
        const friendly =
          result.error === "missing_api_key"
            ? "缺少 API Key"
            : result.error === "timeout_15s"
              ? "请求超时（>15s）"
              : result.error || "未知错误";
        toast.error(`连接失败：${friendly}`);
      }
    },
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : "测试请求失败"),
  });

  const selectedKeyConfigured =
    form.provider === "anthropic"
      ? data?.anthropic_api_key_configured
      : data?.openai_api_key_configured;
  const typedSelectedKey =
    form.provider === "anthropic" ? form.anthropic_api_key : form.openai_api_key;
  const canSave =
    editable &&
    form.default_model.trim() &&
    form.openai_base_url.trim() &&
    form.anthropic_base_url.trim() &&
    (selectedKeyConfigured || typedSelectedKey?.trim());

  function updateField<K extends keyof ModelGatewaySettingsUpdate>(
    key: K,
    value: ModelGatewaySettingsUpdate[K],
  ) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function save() {
    saveMutation.mutate({
      ...form,
      default_model: form.default_model.trim(),
      openai_base_url: form.openai_base_url.trim(),
      openai_api_key: form.openai_api_key?.trim() || null,
      anthropic_base_url: form.anthropic_base_url.trim(),
      anthropic_api_key: form.anthropic_api_key?.trim() || null,
    });
  }

  return (
    <div className="space-y-6">
      <AdminTitle title="系统设置" desc="配置模型服务地址、密钥和默认模型。" />
      {!editable ? (
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="flex items-center gap-3 text-amber-800">
            <LockKeyhole className="size-5" /> 当前角色只能查看。
          </CardContent>
        </Card>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-3">
        <SettingStatusCard
          icon={Server}
          label="运行模式"
          value="真实模型"
          tone="green"
        />
        <SettingStatusCard
          icon={Link2}
          label="当前地址"
          value={data?.active_base_url ?? "-"}
          tone={data?.ready ? "green" : "rose"}
        />
        <SettingStatusCard
          icon={KeyRound}
          label="密钥状态"
          value={selectedKeyConfigured ? "已配置" : "未配置"}
          tone={selectedKeyConfigured ? "green" : "rose"}
        />
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4">
          <div>
            <CardTitle>模型网关</CardTitle>
            <p className="mt-1 text-sm text-slate-500">
              这里保存后，后端生成任务会使用新的 URL 和 Key。
            </p>
          </div>
          <Badge tone={data?.ready ? "green" : "amber"}>
            {isLoading ? "加载中" : data?.ready ? "可用" : "待配置"}
          </Badge>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-3">
            <SegmentButton
              active
              disabled={!editable}
              title="真实模型生产模式"
              desc="所有生成链路直接调用下方 URL 和 Key"
              onClick={() => undefined}
            />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="block text-sm font-bold text-slate-700">
              服务商
              <select
                disabled={!editable}
                value={form.provider}
                onChange={(e) =>
                  updateField(
                    "provider",
                    e.target.value === "anthropic" ? "anthropic" : "openai",
                  )
                }
                className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-4 disabled:bg-slate-100"
              >
                <option value="openai">OpenAI / 兼容接口</option>
                <option value="anthropic">Anthropic</option>
              </select>
            </label>
            <label className="block text-sm font-bold text-slate-700">
              默认模型
              <input
                disabled={!editable}
                value={form.default_model}
                onChange={(e) => updateField("default_model", e.target.value)}
                placeholder="gpt-5.5"
                className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-4 disabled:bg-slate-100"
              />
            </label>
          </div>

          <ProviderFields
            title="OpenAI / 兼容接口"
            active={form.provider === "openai"}
            configured={Boolean(data?.openai_api_key_configured)}
            baseUrl={form.openai_base_url}
            apiKey={form.openai_api_key ?? ""}
            disabled={!editable}
            onBaseUrlChange={(value) => updateField("openai_base_url", value)}
            onApiKeyChange={(value) => updateField("openai_api_key", value)}
            baseUrlPlaceholder="https://api.openai.com/v1"
            keyPlaceholder={
              data?.openai_api_key_configured ? "留空表示保留已有 Key" : "sk-..."
            }
          />

          <ProviderFields
            title="Anthropic"
            active={form.provider === "anthropic"}
            configured={Boolean(data?.anthropic_api_key_configured)}
            baseUrl={form.anthropic_base_url}
            apiKey={form.anthropic_api_key ?? ""}
            disabled={!editable}
            onBaseUrlChange={(value) => updateField("anthropic_base_url", value)}
            onApiKeyChange={(value) => updateField("anthropic_api_key", value)}
            baseUrlPlaceholder="https://api.anthropic.com/v1"
            keyPlaceholder={
              data?.anthropic_api_key_configured ? "留空表示保留已有 Key" : "sk-ant-..."
            }
          />

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-5">
            <p className="text-sm text-slate-500">
              {!canSave
                ? "真实模型模式需要当前服务商的 Key。"
                : "Key 不会在页面回显。可先用「测试连接」验证再保存。"}
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                disabled={!editable || testMutation.isPending}
                onClick={() => testMutation.mutate()}
              >
                <Sparkles className="size-4" />
                {testMutation.isPending ? "测试中…" : "测试连接"}
              </Button>
              <Button disabled={!canSave || saveMutation.isPending} onClick={save}>
                <Save className="size-4" />
                {saveMutation.isPending ? "保存中" : "保存配置"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function SettingStatusCard({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: typeof Server;
  label: string;
  value: string;
  tone: "green" | "amber" | "rose";
}) {
  const toneClass =
    tone === "green"
      ? "bg-emerald-50 text-emerald-700"
      : tone === "amber"
      ? "bg-amber-50 text-amber-700"
      : "bg-rose-50 text-rose-700";
  return (
    <Card>
      <CardContent className="flex items-center gap-3">
        <span className={`grid size-10 shrink-0 place-items-center rounded-xl ${toneClass}`}>
          <Icon className="size-5" />
        </span>
        <div className="min-w-0">
          <p className="text-xs font-bold uppercase text-slate-400">{label}</p>
          <p className="truncate text-sm font-bold text-slate-950">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function SegmentButton({
  active,
  disabled,
  title,
  desc,
  onClick,
}: {
  active: boolean;
  disabled: boolean;
  title: string;
  desc: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`flex min-h-20 items-center justify-between rounded-xl border px-4 text-left transition disabled:cursor-not-allowed disabled:opacity-60 ${
        active
          ? "border-indigo-500 bg-indigo-50 text-indigo-900"
          : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
      }`}
    >
      <span>
        <span className="block font-bold">{title}</span>
        <span className="mt-1 block text-sm opacity-70">{desc}</span>
      </span>
      {active ? <CheckCircle2 className="size-5 shrink-0" /> : null}
    </button>
  );
}

function ProviderFields({
  title,
  active,
  configured,
  baseUrl,
  apiKey,
  disabled,
  onBaseUrlChange,
  onApiKeyChange,
  baseUrlPlaceholder,
  keyPlaceholder,
}: {
  title: string;
  active: boolean;
  configured: boolean;
  baseUrl: string;
  apiKey: string;
  disabled: boolean;
  onBaseUrlChange: (value: string) => void;
  onApiKeyChange: (value: string) => void;
  baseUrlPlaceholder: string;
  keyPlaceholder: string;
}) {
  return (
    <div
      className={`rounded-xl border p-4 ${
        active ? "border-indigo-200 bg-indigo-50/40" : "border-slate-200 bg-white"
      }`}
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="font-bold text-slate-950">{title}</p>
        <Badge tone={configured ? "green" : "slate"}>
          {configured ? "Key 已保存" : "未保存 Key"}
        </Badge>
      </div>
      <div className="grid gap-4 md:grid-cols-[1.2fr_0.8fr]">
        <label className="block text-sm font-bold text-slate-700">
          Base URL
          <input
            disabled={disabled}
            value={baseUrl}
            onChange={(e) => onBaseUrlChange(e.target.value)}
            placeholder={baseUrlPlaceholder}
            className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-4 disabled:bg-slate-100"
          />
        </label>
        <label className="block text-sm font-bold text-slate-700">
          API Key
          <div className="relative mt-2">
            <input
              disabled={disabled}
              value={apiKey}
              onChange={(e) => onApiKeyChange(e.target.value)}
              placeholder={keyPlaceholder}
              type="password"
              className="h-11 w-full rounded-xl border border-slate-200 bg-white px-4 pr-10 disabled:bg-slate-100"
            />
            <EyeOff className="pointer-events-none absolute right-3 top-3 size-5 text-slate-400" />
          </div>
        </label>
      </div>
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
