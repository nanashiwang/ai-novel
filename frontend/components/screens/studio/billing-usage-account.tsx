"use client";

import { useQuery } from "@tanstack/react-query";
import { Bell, Building2, CreditCard, KeyRound, Mail, ShieldCheck, Users, WalletCards } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { Badge, PlanBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { QuotaProgress } from "@/components/ui/progress";
import { billingApi, organizationsApi, quotaApi } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useScopedKey } from "@/lib/use-scoped-key";

export function BillingPage() {
  const { user } = useAuth();
  const { data: plans = [], isPending } = useQuery({
    queryKey: ["billing", "plans"],
    queryFn: () => billingApi.plans(),
  });
  const current = plans.find((p) => p.code === user?.plan_code) ?? plans[0];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-black text-slate-950">账单与套餐</h1>
        <p className="mt-1 text-slate-500">当前组织的 Plan、Feature、Entitlement 和升级入口。</p>
      </div>

      {isPending ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">加载中…</CardContent>
        </Card>
      ) : current ? (
        <Card className="bg-gradient-to-r from-indigo-50 via-white to-emerald-50">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>当前套餐</CardTitle>
            <PlanBadge plan={current.code as never} />
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-4">
            <div className="md:col-span-2">
              <p className="text-4xl font-black text-slate-950">{current.name}</p>
              <p className="mt-2 text-slate-600">{current.description}</p>
              <p className="mt-4 text-2xl font-black text-indigo-600">
                {current.price_monthly ? `¥${current.price_monthly}/月` : "联系销售"}
              </p>
            </div>
            <div className="rounded-2xl bg-white p-4">
              <p className="text-sm text-slate-500">状态</p>
              <p className="mt-2 text-3xl font-black text-slate-950">{current.status}</p>
            </div>
            <div className="rounded-2xl bg-white p-4">
              <p className="text-sm text-slate-500">套餐编码</p>
              <p className="mt-2 text-3xl font-black text-slate-950">{current.code}</p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3">
        {plans
          .filter((p) => p.status === "active")
          .map((plan) => (
            <Card
              key={plan.code}
              className={plan.code === user?.plan_code ? "border-indigo-300" : undefined}
            >
              <CardContent>
                <div className="flex items-center justify-between">
                  <h3 className="text-xl font-black text-slate-950">{plan.name}</h3>
                  {plan.code === user?.plan_code ? <Badge tone="violet">当前</Badge> : null}
                </div>
                <p className="mt-2 min-h-12 text-sm text-slate-500">{plan.description}</p>
                <p className="mt-4 text-2xl font-black">
                  {plan.price_monthly ? `¥${plan.price_monthly}` : "联系销售"}
                </p>
                <Button
                  className="mt-4 w-full"
                  variant={plan.code === user?.plan_code ? "secondary" : "primary"}
                  onClick={async () => {
                    try {
                      const res = await billingApi.checkout(plan.code);
                      toast.success(`已生成结算链接：${res.checkout_url}`);
                    } catch {
                      toast.error("生成支付链接失败");
                    }
                  }}
                >
                  {plan.code === user?.plan_code ? "当前套餐" : "升级"}
                </Button>
              </CardContent>
            </Card>
          ))}
      </div>
    </div>
  );
}

export function UsagePage() {
  const { data: quotas = [], isPending } = useQuery({
    queryKey: useScopedKey("quotas"),
    queryFn: () => quotaApi.list(),
  });
  const { data: usage = [] } = useQuery({
    queryKey: useScopedKey("usage"),
    queryFn: () => quotaApi.usage(),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-black text-slate-950">用量与额度</h1>
        <p className="mt-1 text-slate-500">展示 Quota、Usage、Reservation 和结算状态。</p>
      </div>
      {isPending ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">加载中…</CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {quotas.map((quota) => (
            <Card key={quota.id}>
              <CardContent>
                <div className="mb-3 flex items-center justify-between">
                  <p className="font-bold text-slate-950">{quota.quota_key}</p>
                  <Badge tone="blue">Quota</Badge>
                </div>
                <QuotaProgress
                  used={quota.used_value}
                  reserved={quota.reserved_value}
                  limit={quota.limit_value}
                />
                <p className="mt-3 text-xs text-slate-500">
                  重置时间：{formatDateTime(quota.reset_at)}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Usage Events</CardTitle>
        </CardHeader>
        <CardContent>
          {usage.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">暂无用量事件。</p>
          ) : (
            <DataTable
              rows={usage}
              columns={[
                {
                  key: "type",
                  header: "事件",
                  render: (row) => <span className="font-bold text-slate-950">{row.event_type}</span>,
                },
                {
                  key: "amount",
                  header: "数量",
                  render: (row) => `${row.amount.toLocaleString()} ${row.unit}`,
                },
                { key: "job", header: "generation_job", render: (row) => row.job_id ?? "-" },
                { key: "project", header: "project", render: (row) => row.project_id ?? "-" },
                { key: "time", header: "时间", render: (row) => formatDateTime(row.created_at) },
              ]}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function AccountPage() {
  const { user } = useAuth();
  const { data: members = [] } = useQuery({
    queryKey: useScopedKey("members"),
    queryFn: () => organizationsApi.members(),
    enabled: !!user,
  });

  if (!user) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-black text-slate-950">账号 / 组织设置</h1>
        <p className="mt-1 text-slate-500">用户资料、组织信息、成员、API Key 预留与通知。</p>
      </div>
      <div className="grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
        <Card>
          <CardHeader>
            <CardTitle>用户资料</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <SettingRow icon={Mail} label="邮箱" value={user.email} />
            <SettingRow icon={ShieldCheck} label="组织角色" value={user.organization_role} />
            <SettingRow icon={WalletCards} label="当前套餐" value={user.plan_code} />
            <Button onClick={() => toast.info("用户资料更新接口待对接")}>保存资料</Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>组织信息</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <SettingRow icon={Building2} label="组织名称" value={user.organization_name} />
            <SettingRow icon={ShieldCheck} label="组织 ID" value={user.organization_id} />
            <div className="rounded-2xl bg-slate-50 p-4">
              <p className="font-bold text-slate-950">API Key 预留</p>
              <p className="mt-1 text-sm text-slate-500">
                Pro/Team/Enterprise 可见，本阶段未启用真实 key。
              </p>
              <Button
                className="mt-3"
                variant="secondary"
                onClick={() => toast.info("API Key 接口待对接")}
              >
                <KeyRound className="size-4" /> 创建 API Key
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>成员管理</CardTitle>
        </CardHeader>
        <CardContent>
          {members.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">暂无成员（含当前用户）。</p>
          ) : (
            <DataTable
              rows={members}
              columns={[
                { key: "user", header: "user_id", render: (row) => row.user_id },
                { key: "org", header: "organization_id", render: (row) => row.organization_id },
                {
                  key: "role",
                  header: "角色",
                  render: (row) => <Badge tone="violet">{row.role}</Badge>,
                },
                {
                  key: "status",
                  header: "状态",
                  render: (row) => (
                    <StatusBadge status={row.status === "active" ? "succeeded" : "queued"} />
                  ),
                },
              ]}
            />
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>通知设置</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-3">
          <SettingPill icon={Bell} text="任务失败通知" />
          <SettingPill icon={CreditCard} text="额度低于 20% 提醒" />
          <SettingPill icon={Users} text="成员变更提醒" />
        </CardContent>
      </Card>
    </div>
  );
}

function SettingRow({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Mail;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between rounded-2xl border border-slate-200 p-4">
      <div className="flex items-center gap-3">
        <Icon className="size-5 text-indigo-600" />
        <span className="font-semibold text-slate-600">{label}</span>
      </div>
      <span className="font-bold text-slate-950">{value}</span>
    </div>
  );
}

function SettingPill({ icon: Icon, text }: { icon: typeof Bell; text: string }) {
  return (
    <button
      type="button"
      className="flex items-center justify-center gap-2 rounded-2xl border border-slate-200 p-4 font-semibold text-slate-700 hover:bg-slate-50"
    >
      <Icon className="size-5 text-indigo-600" />
      {text}
    </button>
  );
}
