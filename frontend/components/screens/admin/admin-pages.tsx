"use client";

import { useState } from "react";
import { Area, AreaChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import { AlertTriangle, Building2, Cog, LockKeyhole, Save, Sparkles, Users } from "lucide-react";
import { useMockAuth } from "@/components/providers/mock-auth-provider";
import { Badge, PlanBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { ModelCallTable } from "@/components/ui/model-call-table";
import { ProgressBar, QuotaProgress } from "@/components/ui/progress";
import { StatCard } from "@/components/ui/stat-card";
import { WorkflowSteps } from "@/components/ui/workflow-steps";
import { auditLogs, contentReviews, jobs, modelCalls, organizations, planFeatures, plans, platformTrend, platformUsers, quotas, workflowSteps } from "@/lib/mock-data";
import { isSuperAdmin } from "@/lib/permissions";
import { formatDateTime } from "@/lib/format";

export function AdminDashboardPage() {
  return (
    <div className="space-y-6">
      <AdminTitle title="Admin 后台总览" desc="平台级运营数据、任务队列、系统状态和告警。" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="注册用户" value="12,840" delta="+12.4%" icon={Users} tone="blue" />
        <StatCard label="付费组织" value="824" delta="+6.8%" icon={Building2} tone="green" />
        <StatCard label="今日生成字数" value="214 万" delta="+18.6%" icon={Sparkles} tone="violet" />
        <StatCard label="失败任务" value="17" delta="需处理" icon={AlertTriangle} tone="orange" />
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <Card><CardHeader><CardTitle>近 7 日趋势</CardTitle></CardHeader><CardContent className="overflow-x-auto"><AreaChart width={720} height={300} data={platformTrend}><defs><linearGradient id="words" x1="0" x2="0" y1="0" y2="1"><stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} /><stop offset="95%" stopColor="#6366f1" stopOpacity={0} /></linearGradient></defs><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="day" /><YAxis /><Tooltip /><Area type="monotone" dataKey="words" stroke="#6366f1" fill="url(#words)" name="生成字数（万）" /></AreaChart></CardContent></Card>
        <Card><CardHeader><CardTitle>运营告警 / 系统状态</CardTitle></CardHeader><CardContent className="space-y-3"><AlertItem tone="rose" title="模型调用错误率 2.1%" text="高于昨日均值，建议检查 gpt-4o 队列。" /><AlertItem tone="amber" title="Pro 额度消耗异常" text="personal-workspace 今日消耗高于 7 日均值。" /><AlertItem tone="green" title="Temporal Worker 正常" text="scene / outline / review worker 均在线。" /></CardContent></Card>
      </div>
      <Card><CardHeader><CardTitle>最新生成任务</CardTitle></CardHeader><CardContent><AdminJobsTable rows={jobs} /></CardContent></Card>
    </div>
  );
}

function AdminTitle({ title, desc }: { title: string; desc: string }) {
  return <div><h1 className="text-3xl font-black text-slate-950">{title}</h1><p className="mt-1 text-slate-500">{desc}</p></div>;
}

function AlertItem({ tone, title, text }: { tone: "rose" | "amber" | "green"; title: string; text: string }) {
  const color = tone === "rose" ? "bg-rose-50 text-rose-700" : tone === "amber" ? "bg-amber-50 text-amber-700" : "bg-emerald-50 text-emerald-700";
  return <div className={`rounded-2xl p-4 ${color}`}><p className="font-bold">{title}</p><p className="mt-1 text-sm opacity-80">{text}</p></div>;
}

export function AdminUsersPage() {
  return (
    <div className="space-y-6">
      <AdminTitle title="用户管理" desc="平台用户、角色、状态、封禁 / 恢复操作。" />
      <DataTable rows={platformUsers} columns={[{ key: "name", header: "用户", render: (row) => <div><p className="font-bold text-slate-950">{row.name}</p><p className="text-xs text-slate-500">{row.email}</p></div> }, { key: "role", header: "角色", render: (row) => <Badge tone={row.role === "super_admin" ? "amber" : "blue"}>{row.role}</Badge> }, { key: "org", header: "组织", render: (row) => row.organization }, { key: "plan", header: "套餐", render: (row) => <PlanBadge plan={row.plan} /> }, { key: "status", header: "状态", render: (row) => <StatusBadge status={row.status === "active" ? "succeeded" : "failed"} /> }, { key: "seen", header: "最近活跃", render: (row) => row.lastSeen }, { key: "actions", header: "操作", render: (row) => <div className="flex gap-2"><Button size="sm" variant="secondary" onClick={() => toast.info(`查看 ${row.email}`)}>查看</Button><Button size="sm" variant="danger" onClick={() => toast.warning("封禁/恢复会写入 audit_logs（mock）")}>封禁</Button></div> }]} />
    </div>
  );
}

export function AdminOrganizationsPage() {
  return (
    <div className="space-y-6">
      <AdminTitle title="组织管理" desc="组织状态、套餐、成员和额度入口。" />
      <DataTable rows={organizations} columns={[{ key: "name", header: "组织", render: (row) => <span className="font-bold text-slate-950">{row.name}</span> }, { key: "owner", header: "owner_user_id", render: (row) => row.ownerUserId }, { key: "plan", header: "Plan", render: (row) => <PlanBadge plan={row.planCode} /> }, { key: "status", header: "状态", render: (row) => <StatusBadge status={row.status === "active" ? "succeeded" : row.status === "trialing" ? "queued" : "failed"} /> }, { key: "created", header: "创建时间", render: (row) => row.createdAt.slice(0, 10) }, { key: "actions", header: "操作", render: () => <div className="flex gap-2"><Button size="sm" variant="secondary">成员</Button><Button size="sm" variant="secondary">额度</Button></div> }]} />
    </div>
  );
}

export function AdminPlansPage() {
  return (
    <div className="space-y-6">
      <AdminTitle title="套餐 / 权益管理" desc="Plan、Feature、Entitlement 配置，修改会写入 audit_logs。" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">{plans.map((plan) => <Card key={plan.code}><CardContent><PlanBadge plan={plan.code} /><h3 className="mt-3 text-xl font-black text-slate-950">{plan.name}</h3><p className="mt-2 min-h-12 text-sm text-slate-500">{plan.description}</p><p className="mt-3 text-sm font-semibold text-slate-600">并发 {plan.maxConcurrentJobs} · {plan.queuePriority}</p><Button className="mt-4 w-full" variant="secondary" onClick={() => toast.info("套餐修改将写入 audit_logs（mock）")}>编辑套餐</Button></CardContent></Card>)}</div>
      <Card><CardHeader><CardTitle>plan_features 表格</CardTitle></CardHeader><CardContent><DataTable rows={planFeatures} columns={[{ key: "plan", header: "Plan", render: (row) => <PlanBadge plan={row.planCode} /> }, { key: "feature", header: "Feature", render: (row) => <div><p className="font-bold text-slate-950">{row.featureName}</p><p className="text-xs text-slate-500">{row.featureKey}</p></div> }, { key: "enabled", header: "enabled", render: (row) => <StatusBadge status={row.enabled ? "succeeded" : "failed"} /> }, { key: "limit", header: "limit", render: (row) => `${row.limitValue} ${row.limitUnit}` }, { key: "action", header: "操作", render: () => <Button size="sm" variant="secondary" onClick={() => toast.info("保存后写入 audit_logs（mock）")}>修改</Button> }]} /></CardContent></Card>
    </div>
  );
}

export function AdminQuotasPage() {
  return (
    <div className="space-y-6">
      <AdminTitle title="额度管理" desc="组织额度、预留额度、手动调整工具和审计提示。" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">{quotas.map((quota) => <Card key={quota.id}><CardContent><div className="mb-3 flex items-center justify-between"><p className="font-bold text-slate-950">{quota.label}</p><Badge tone="blue">{quota.quotaKey}</Badge></div><QuotaProgress used={quota.usedValue} reserved={quota.reservedValue} limit={quota.limitValue} /></CardContent></Card>)}</div>
      <Card><CardHeader><CardTitle>手动额度调整工具</CardTitle></CardHeader><CardContent className="grid gap-4 md:grid-cols-4"><input className="h-11 rounded-xl border border-slate-200 px-4" defaultValue="personal-workspace" /><input className="h-11 rounded-xl border border-slate-200 px-4" defaultValue="monthly_generated_words" /><input className="h-11 rounded-xl border border-slate-200 px-4" defaultValue="20000" /><Button onClick={() => toast.warning("额度调整已 mock，实际会写入 audit_logs")}>调整额度</Button><p className="md:col-span-4 text-sm text-amber-700">所有额度调整必须记录 actor、reason、before/after 和 request_id。</p></CardContent></Card>
    </div>
  );
}

export function AdminGenerationJobsPage() {
  const [rows, setRows] = useState(jobs);
  return (
    <div className="space-y-6">
      <AdminTitle title="平台生成队列" desc="平台级 generation_jobs，支持强制取消、重试和 workflow 观察。" />
      <Card><CardHeader><CardTitle>Workflow 概览</CardTitle></CardHeader><CardContent><WorkflowSteps steps={workflowSteps} /></CardContent></Card>
      <Card><CardHeader><CardTitle>generation_jobs</CardTitle></CardHeader><CardContent><AdminJobsTable rows={rows} onCancel={(id) => { setRows((current) => current.map((job) => job.id === id ? { ...job, status: "cancelled" } : job)); toast.warning("已强制取消任务，将写入 audit_logs（mock）"); }} onRetry={(id) => { setRows((current) => current.map((job) => job.id === id ? { ...job, status: "queued", progress: 0 } : job)); toast.success("已强制重试任务，将写入 audit_logs（mock）"); }} /></CardContent></Card>
    </div>
  );
}

function AdminJobsTable({ rows, onCancel, onRetry }: { rows: typeof jobs; onCancel?: (id: string) => void; onRetry?: (id: string) => void }) {
  return <DataTable rows={rows} columns={[{ key: "title", header: "任务", render: (row) => <div><p className="font-bold text-slate-950">{row.title}</p><p className="text-xs text-slate-500">{row.workflowRunId}</p></div> }, { key: "org", header: "organization_id", render: (row) => row.organizationId }, { key: "type", header: "task_type", render: (row) => row.taskType }, { key: "status", header: "状态", render: (row) => <StatusBadge status={row.status} /> }, { key: "quota", header: "额度", render: (row) => `${row.consumedQuota}/${row.reservedQuota}` }, { key: "progress", header: "进度", render: (row) => <ProgressBar value={row.progress} /> }, { key: "action", header: "强制操作", render: (row) => <div className="flex gap-2"><Button size="sm" variant="danger" onClick={() => onCancel?.(row.id)}>取消</Button><Button size="sm" variant="secondary" onClick={() => onRetry?.(row.id)}>重试</Button></div> }]} />;
}

export function AdminModelCallsPage() {
  return (
    <div className="space-y-6">
      <AdminTitle title="模型调用日志" desc="ModelGateway 统一记录 task_type、model、token、latency、status 和 Prompt / Response 摘要。" />
      <ModelCallTable rows={modelCalls} />
      <div className="grid gap-4 xl:grid-cols-2">{modelCalls.slice(0, 2).map((call) => <Card key={call.id}><CardHeader><CardTitle>{call.taskType} · {call.model}</CardTitle></CardHeader><CardContent className="space-y-4"><BibleLog title="Prompt 预览" text={call.promptPreview} /><BibleLog title="Response 预览" text={call.responsePreview} /><p className="text-sm text-slate-500">cost: ${call.costUsd} · latency: {call.latencyMs}ms</p></CardContent></Card>)}</div>
    </div>
  );
}

function BibleLog({ title, text }: { title: string; text: string }) {
  return <div className="rounded-2xl bg-slate-50 p-4"><p className="font-bold text-slate-950">{title}</p><p className="mt-2 text-sm leading-6 text-slate-600">{text}</p></div>;
}

export function AdminContentReviewPage() {
  return (
    <div className="space-y-6">
      <AdminTitle title="内容审核 / 风控" desc="当前无独立参考图，按 Admin 风格实现待审核内容、风险等级、处理动作。" />
      <DataTable rows={contentReviews} columns={[{ key: "title", header: "内容", render: (row) => <div><p className="font-bold text-slate-950">{row.title}</p><p className="text-xs text-slate-500">{row.organization} / {row.project}</p></div> }, { key: "risk", header: "风险", render: (row) => <Badge tone={row.risk === "高" ? "rose" : row.risk === "中" ? "amber" : "green"}>{row.risk}</Badge> }, { key: "model", header: "策略", render: (row) => row.model }, { key: "status", header: "状态", render: (row) => row.status }, { key: "time", header: "时间", render: (row) => row.createdAt }, { key: "action", header: "处理", render: () => <div className="flex gap-2"><Button size="sm" onClick={() => toast.success("已放行，写入审核日志（mock）")}>放行</Button><Button size="sm" variant="danger" onClick={() => toast.warning("已拦截，写入审核日志（mock）")}>拦截</Button></div> }]} />
    </div>
  );
}

export function AdminSettingsPage() {
  const { user } = useMockAuth();
  const editable = isSuperAdmin(user);
  return (
    <div className="space-y-6">
      <AdminTitle title="系统设置" desc="模型配置、Prompt 版本、队列配置和权限矩阵；仅 super_admin 可修改。" />
      {!editable ? <Card className="border-amber-200 bg-amber-50"><CardContent className="flex items-center gap-3 text-amber-800"><LockKeyhole className="size-5" /> 当前角色只能查看，保存按钮 disabled。</CardContent></Card> : null}
      <div className="grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
        <Card><CardHeader><CardTitle>设置导航</CardTitle></CardHeader><CardContent className="space-y-2">{["模型配置", "Prompt 版本", "队列配置", "权限矩阵", "审计策略"].map((item) => <button key={item} type="button" className="flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left font-semibold text-slate-700 hover:bg-slate-50"><Cog className="size-4 text-indigo-600" />{item}</button>)}</CardContent></Card>
        <Card><CardHeader className="flex flex-row items-center justify-between"><CardTitle>模型配置</CardTitle><Badge tone={editable ? "green" : "amber"}>{editable ? "super_admin 可编辑" : "只读"}</Badge></CardHeader><CardContent className="grid gap-4 md:grid-cols-2"><ConfigInput label="默认文本模型" value="gpt-4o" disabled={!editable} /><ConfigInput label="默认 JSON 模型" value="gpt-4o-mini" disabled={!editable} /><ConfigInput label="temperature" value="0.75" disabled={!editable} /><ConfigInput label="max_context" value="128k" disabled={!editable} /><Button disabled={!editable} onClick={() => toast.success("系统设置已保存，将写入 audit_logs（mock）")}><Save className="size-4" /> 保存系统设置</Button></CardContent></Card>
      </div>
      <Card><CardHeader><CardTitle>Prompt 版本表格</CardTitle></CardHeader><CardContent><DataTable rows={[{ name: "scene_draft", version: "v18", status: "active" }, { name: "outline_planner", version: "v11", status: "active" }, { name: "continuity_review", version: "v7", status: "draft" }]} columns={[{ key: "name", header: "Prompt", render: (row) => <span className="font-bold text-slate-950">{row.name}</span> }, { key: "version", header: "版本", render: (row) => row.version }, { key: "status", header: "状态", render: (row) => <StatusBadge status={row.status === "active" ? "succeeded" : "queued"} /> }, { key: "action", header: "操作", render: () => <Button disabled={!editable} size="sm" variant="secondary">发布</Button> }]} /></CardContent></Card>
      <Card><CardHeader><CardTitle>队列配置</CardTitle></CardHeader><CardContent className="grid gap-4 md:grid-cols-3"><QueueCard title="scene-high" worker="8" status="healthy" /><QueueCard title="outline-normal" worker="4" status="healthy" /><QueueCard title="review-normal" worker="3" status="degraded" /></CardContent></Card>
    </div>
  );
}

function ConfigInput({ label, value, disabled }: { label: string; value: string; disabled: boolean }) {
  return <label className="block text-sm font-bold text-slate-700">{label}<input disabled={disabled} className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-4 disabled:bg-slate-100" defaultValue={value} /></label>;
}

function QueueCard({ title, worker, status }: { title: string; worker: string; status: string }) {
  return <div className="rounded-2xl border border-slate-200 p-4"><p className="font-black text-slate-950">{title}</p><p className="mt-2 text-sm text-slate-500">workers: {worker}</p><StatusBadge status={status === "healthy" ? "succeeded" : "queued"} /></div>;
}

export function AdminAuditLogsPage() {
  return (
    <div className="space-y-6">
      <AdminTitle title="审计日志" desc="所有管理员破坏性操作、套餐、额度和系统设置变更都必须记录。" />
      <DataTable rows={auditLogs} columns={[{ key: "actor", header: "actor", render: (row) => <span className="font-bold text-slate-950">{row.actor}</span> }, { key: "action", header: "action", render: (row) => row.action }, { key: "resource", header: "resource", render: (row) => row.resource }, { key: "target", header: "target", render: (row) => row.target }, { key: "ip", header: "ip", render: (row) => row.ip }, { key: "time", header: "时间", render: (row) => formatDateTime(row.createdAt) }]} />
    </div>
  );
}
