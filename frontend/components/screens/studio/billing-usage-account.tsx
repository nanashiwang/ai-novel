"use client";

import { toast } from "sonner";
import { Bell, Building2, CreditCard, KeyRound, Mail, ShieldCheck, Users, WalletCards } from "lucide-react";
import { Badge, PlanBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { QuotaProgress } from "@/components/ui/progress";
import { plans, planFeatures, quotas, usageEvents, members, organizations } from "@/lib/mock-data";
import { formatDateTime } from "@/lib/format";

export function BillingPage() {
  const current = plans.find((plan) => plan.code === "Pro") ?? plans[2];
  return (
    <div className="space-y-6">
      <div><h1 className="text-3xl font-black text-slate-950">账单与套餐</h1><p className="mt-1 text-slate-500">当前组织的 Plan、Feature、Entitlement 和升级入口。</p></div>
      <Card className="bg-gradient-to-r from-indigo-50 via-white to-emerald-50">
        <CardHeader className="flex flex-row items-center justify-between"><CardTitle>当前套餐</CardTitle><PlanBadge plan={current.code} /></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-4">
          <div className="md:col-span-2"><p className="text-4xl font-black text-slate-950">{current.name}</p><p className="mt-2 text-slate-600">{current.description}</p><p className="mt-4 text-2xl font-black text-indigo-600">¥{current.priceMonthly}/月</p></div>
          <div className="rounded-2xl bg-white p-4"><p className="text-sm text-slate-500">并发任务</p><p className="mt-2 text-3xl font-black text-slate-950">{current.maxConcurrentJobs}</p></div>
          <div className="rounded-2xl bg-white p-4"><p className="text-sm text-slate-500">队列优先级</p><p className="mt-2 text-3xl font-black text-slate-950">{current.queuePriority}</p></div>
        </CardContent>
      </Card>
      <div className="grid gap-4 md:grid-cols-3">{plans.filter((p) => p.status === "active").map((plan) => <Card key={plan.code} className={plan.code === "Pro" ? "border-indigo-300" : undefined}><CardContent><div className="flex items-center justify-between"><h3 className="text-xl font-black text-slate-950">{plan.name}</h3>{plan.code === "Pro" ? <Badge tone="violet">当前</Badge> : null}</div><p className="mt-2 min-h-12 text-sm text-slate-500">{plan.description}</p><p className="mt-4 text-2xl font-black">{plan.priceMonthly ? `¥${plan.priceMonthly}` : "联系销售"}</p><Button className="mt-4 w-full" variant={plan.code === "Pro" ? "secondary" : "primary"} onClick={() => toast.info("套餐切换为 mock action，将写入 billing events")}>{plan.code === "Pro" ? "当前套餐" : "升级"}</Button></CardContent></Card>)}</div>
      <Card><CardHeader><CardTitle>Plan Features / Entitlements</CardTitle></CardHeader><CardContent><DataTable rows={planFeatures} columns={[{ key: "plan", header: "Plan", render: (row) => <PlanBadge plan={row.planCode} /> }, { key: "feature", header: "Feature", render: (row) => <div><p className="font-bold text-slate-950">{row.featureName}</p><p className="text-xs text-slate-500">{row.featureKey}</p></div> }, { key: "enabled", header: "Entitlement", render: (row) => <StatusBadge status={row.enabled ? "succeeded" : "failed"} /> }, { key: "limit", header: "Limit", render: (row) => `${row.limitValue} ${row.limitUnit}` }, { key: "desc", header: "说明", render: (row) => row.description }]} /></CardContent></Card>
    </div>
  );
}

export function UsagePage() {
  return (
    <div className="space-y-6">
      <div><h1 className="text-3xl font-black text-slate-950">用量与额度</h1><p className="mt-1 text-slate-500">展示 Quota、Usage、Reservation 和结算状态。</p></div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">{quotas.map((quota) => <Card key={quota.id}><CardContent><div className="mb-3 flex items-center justify-between"><p className="font-bold text-slate-950">{quota.label}</p><Badge tone="blue">Quota</Badge></div><QuotaProgress used={quota.usedValue} reserved={quota.reservedValue} limit={quota.limitValue} /><p className="mt-3 text-xs text-slate-500">重置时间：{quota.resetAt}</p></CardContent></Card>)}</div>
      <Card><CardHeader><CardTitle>Usage Events</CardTitle></CardHeader><CardContent><DataTable rows={usageEvents} columns={[{ key: "type", header: "事件", render: (row) => <span className="font-bold text-slate-950">{row.eventType}</span> }, { key: "amount", header: "数量", render: (row) => `${row.amount.toLocaleString()} ${row.unit}` }, { key: "job", header: "generation_job", render: (row) => row.generationJobId ?? "-" }, { key: "project", header: "project", render: (row) => row.projectId ?? "-" }, { key: "time", header: "时间", render: (row) => formatDateTime(row.createdAt) }]} /></CardContent></Card>
    </div>
  );
}

export function AccountPage() {
  return (
    <div className="space-y-6">
      <div><h1 className="text-3xl font-black text-slate-950">账号 / 组织设置</h1><p className="mt-1 text-slate-500">用户资料、组织信息、成员、API Key 预留与通知。</p></div>
      <div className="grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
        <Card><CardHeader><CardTitle>用户资料</CardTitle></CardHeader><CardContent className="space-y-4"><SettingRow icon={Mail} label="邮箱" value="writer@example.com" /><SettingRow icon={ShieldCheck} label="组织角色" value="owner" /><SettingRow icon={WalletCards} label="当前套餐" value="Pro" /><Button onClick={() => toast.success("资料已保存（mock）")}>保存资料</Button></CardContent></Card>
        <Card><CardHeader><CardTitle>组织信息</CardTitle></CardHeader><CardContent className="space-y-4"><SettingRow icon={Building2} label="组织名称" value={organizations[0].name} /><SettingRow icon={ShieldCheck} label="组织状态" value={organizations[0].status} /><div className="rounded-2xl bg-slate-50 p-4"><p className="font-bold text-slate-950">API Key 预留</p><p className="mt-1 text-sm text-slate-500">Pro/Team/Enterprise 可见，本阶段不生成真实 key。</p><Button className="mt-3" variant="secondary" onClick={() => toast.info("API Key 为 mock action") }><KeyRound className="size-4" /> 创建 API Key</Button></div></CardContent></Card>
      </div>
      <Card><CardHeader><CardTitle>成员管理</CardTitle></CardHeader><CardContent><DataTable rows={members} columns={[{ key: "user", header: "user_id", render: (row) => row.userId }, { key: "org", header: "organization_id", render: (row) => row.organizationId }, { key: "role", header: "角色", render: (row) => <Badge tone="violet">{row.role}</Badge> }, { key: "status", header: "状态", render: (row) => <StatusBadge status={row.status === "active" ? "succeeded" : "queued"} /> }, { key: "joined", header: "加入时间", render: (row) => row.joinedAt.slice(0, 10) }]} /></CardContent></Card>
      <Card><CardHeader><CardTitle>通知设置</CardTitle></CardHeader><CardContent className="grid gap-3 md:grid-cols-3"><SettingPill icon={Bell} text="任务失败通知" /><SettingPill icon={CreditCard} text="额度低于 20% 提醒" /><SettingPill icon={Users} text="成员变更提醒" /></CardContent></Card>
    </div>
  );
}

function SettingRow({ icon: Icon, label, value }: { icon: typeof Mail; label: string; value: string }) {
  return <div className="flex items-center justify-between rounded-2xl border border-slate-200 p-4"><div className="flex items-center gap-3"><Icon className="size-5 text-indigo-600" /><span className="font-semibold text-slate-600">{label}</span></div><span className="font-bold text-slate-950">{value}</span></div>;
}

function SettingPill({ icon: Icon, text }: { icon: typeof Bell; text: string }) {
  return <button type="button" className="flex items-center justify-center gap-2 rounded-2xl border border-slate-200 p-4 font-semibold text-slate-700 hover:bg-slate-50"><Icon className="size-5 text-indigo-600" />{text}</button>;
}
