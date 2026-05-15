"use client";

import { useState } from "react";
import { toast } from "sonner";
import {
  BookOpen,
  Boxes,
  CheckCircle2,
  Download,
  FileArchive,
  LockKeyhole,
  Network,
  RefreshCw,
  Save,
  Sparkles,
  TimerReset,
  Users,
  Wand2,
  XCircle,
} from "lucide-react";
import { ProjectHeader } from "./project-frame";
import { ActionCard } from "@/components/ui/action-card";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { EditorMock } from "@/components/ui/editor-mock";
import { ModelCallTable } from "@/components/ui/model-call-table";
import { ProgressBar, QuotaProgress } from "@/components/ui/progress";
import { WorkflowSteps } from "@/components/ui/workflow-steps";
import {
  characters,
  chapters,
  exportsData,
  issues,
  jobs,
  modelCalls,
  novelSpecs,
  quotas,
  reservations,
  scenes,
  workflowSteps,
  worldItems,
} from "@/lib/mock-data";
import { formatDateTime } from "@/lib/format";
import type { ExportFile, GenerationJob } from "@/types";

export function BiblePage({ projectId }: { projectId: string }) {
  const spec = novelSpecs[0];
  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between"><CardTitle>故事圣经 Story Bible</CardTitle><Badge tone="blue">版本 v12</Badge></CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <BibleBlock title="Premise" text={spec.premise} />
            <BibleBlock title="Theme" text={spec.theme} />
            <BibleBlock title="核心卖点" text="地下档案、记忆抹除、家族物证、城市级阴谋。" />
            <BibleBlock title="主线冲突" text="陆沉舟寻找真相，但证据逐步指向他本人曾经参与抹除。" />
            <BibleBlock title="叙事规则" text={spec.narrativePov} />
            <BibleBlock title="文风规则" text={spec.styleGuide} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>生成控制</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-2xl bg-indigo-50 p-4 text-sm leading-6 text-indigo-700">故事圣经是大纲、人物、世界观和场景生成的上游源。修改后会提示重新生成下游上下文。</div>
            <div className="space-y-2">{spec.constraints.map((item) => <div key={item} className="flex items-center gap-2 text-sm text-slate-700"><LockKeyhole className="size-4 text-amber-500" />{item}</div>)}</div>
            <Button onClick={() => toast.success("已启动 StoryBibleWorkflow（mock）")}><Sparkles className="size-4" /> 重新生成故事圣经</Button>
            <Button variant="secondary" onClick={() => toast.success("已保存为故事圣经版本 v13（mock）")}><Save className="size-4" /> 保存版本</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function BibleBlock({ title, text }: { title: string; text: string }) {
  return <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><p className="text-sm font-black text-slate-950">{title}</p><p className="mt-2 text-sm leading-6 text-slate-600">{text}</p></div>;
}

export function CharactersPage({ projectId }: { projectId: string }) {
  const [activeId, setActiveId] = useState(characters[0].id);
  const active = characters.find((character) => character.id === activeId) ?? characters[0];
  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <div className="grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
        <Card>
          <CardHeader><CardTitle>人物列表</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {characters.map((character) => (
              <button key={character.id} type="button" onClick={() => setActiveId(character.id)} className={`w-full rounded-2xl border p-4 text-left transition ${activeId === character.id ? "border-indigo-300 bg-indigo-50" : "border-slate-200 hover:bg-slate-50"}`}>
                <div className="flex items-center justify-between"><p className="font-bold text-slate-950">{character.name}</p><Badge tone="violet">{character.role}</Badge></div>
                <p className="mt-1 text-sm text-slate-500">{character.archetype}</p>
                <p className="mt-2 text-xs text-emerald-700">Memory Engine 自动更新：{character.status}</p>
              </button>
            ))}
          </CardContent>
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle>人物详情：{active.name}</CardTitle></CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <BibleBlock title="当前目标" text={active.currentGoal} />
              <BibleBlock title="隐藏秘密" text={active.secret} />
              <BibleBlock title="角色状态" text={active.status} />
              <BibleBlock title="关系标签" text={active.relationshipTags.join("；")} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>人物关系图</CardTitle></CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-3">
                {characters.map((character) => <div key={character.id} className="rounded-2xl border border-slate-200 bg-white p-4 text-center"><div className="mx-auto grid size-12 place-items-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 text-lg font-black text-white">{character.name.slice(0, 1)}</div><p className="mt-2 font-bold text-slate-950">{character.name}</p><p className="text-xs text-slate-500">{character.role}</p></div>)}
              </div>
              <div className="mt-4 rounded-2xl bg-slate-50 p-4 text-sm text-slate-600"><Network className="mr-2 inline size-4 text-indigo-600" />关系边：互信建立中、隐秘血缘、血脉绑定。章节推进后由 Memory Engine 写入状态时间线。</div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

export function WorldPage({ projectId }: { projectId: string }) {
  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {worldItems.map((item) => <Card key={item.id}><CardContent><Badge tone="blue">{item.type}</Badge><h3 className="mt-3 text-lg font-black text-slate-950">{item.name}</h3><p className="mt-2 text-sm leading-6 text-slate-500">{item.summary}</p><p className="mt-3 text-xs font-semibold text-indigo-600">引用：{item.references.join(" / ")}</p></CardContent></Card>)}
      </div>
      <Card>
        <CardHeader><CardTitle>Lorebook 检索</CardTitle></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
          <ActionCard title="地点" description="档案馆、地下库房、雾都旧街区" href="#" icon={Boxes} tone="violet" />
          <ActionCard title="组织" description="档案委员会、守门人系统" href="#" icon={Users} tone="blue" />
          <ActionCard title="规则" description="归档计划、记忆残影、血脉密钥" href="#" icon={BookOpen} tone="green" />
        </CardContent>
      </Card>
    </div>
  );
}

export function OutlinePage({ projectId }: { projectId: string }) {
  const activeChapter = chapters[2];
  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <div className="grid gap-4 xl:grid-cols-[0.75fr_1.25fr]">
        <Card>
          <CardHeader><CardTitle>卷 / 章 / 场景大纲树</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="font-bold text-slate-950">卷一 · 迷雾之城 <span className="ml-2 text-xs text-slate-500">共 18 章</span></div>
            {chapters.map((chapter) => <div key={chapter.id} className={`rounded-2xl border p-4 ${chapter.id === activeChapter.id ? "border-indigo-300 bg-indigo-50" : "border-slate-200"}`}><div className="flex items-center justify-between"><p className="font-bold text-slate-950">第{chapter.chapterIndex}章 · {chapter.title}</p><StatusBadge status={chapter.status} /></div><p className="mt-1 text-sm text-slate-500">{chapter.summary}</p></div>)}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between"><CardTitle>当前章节大纲</CardTitle><Badge tone="violet">可生成场景拆分</Badge></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <BibleBlock title="章节目标" text={activeChapter.goal} />
              <BibleBlock title="核心冲突" text={activeChapter.conflict} />
              <BibleBlock title="人物变化" text="陆沉舟从怀疑苏晚转向怀疑自己的过去；苏晚暴露一处轻微破绽。" />
              <BibleBlock title="信息揭示" text="归档计划需要家族血脉密钥，713 铁盒保存父亲旧案。" />
              <BibleBlock title="结尾钩子" text={activeChapter.endingHook} />
              <BibleBlock title="关联伏笔" text="禁阅索引、守门人编号、陆家旧签名。" />
            </div>
            <DataTable
              rows={scenes}
              columns={[
                { key: "scene", header: "场景", render: (row) => <span className="font-bold text-slate-950">场景{row.sceneIndex} · {row.title}</span> },
                { key: "location", header: "地点", render: (row) => row.location },
                { key: "goal", header: "目标", render: (row) => row.goal },
                { key: "status", header: "状态", render: (row) => <StatusBadge status={row.status} /> },
              ]}
            />
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-slate-50 p-4"><div><p className="font-bold text-slate-950">额度预估：12,000 字</p><p className="text-sm text-slate-500">Pro 权益允许章节级大纲生成，正文仍按 scene 生成。</p></div><Button onClick={() => toast.success("已启动 OutlineWorkflow（mock）")}><Wand2 className="size-4" /> 生成大纲</Button></div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export function WritingWorkspacePage({ projectId }: { projectId: string }) {
  const [activeTab, setActiveTab] = useState("记忆");
  const tabs = ["记忆", "人物", "世界观", "审稿"];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><p className="text-sm text-slate-500">工作台 / 项目 / {projectId} / 写作</p><h1 className="text-2xl font-black text-slate-950">第13章 · 地下库房的秘密 <span className="text-slate-400">/</span> 场景2：地下库房 <StatusBadge status="drafting" /></h1><p className="mt-1 text-sm text-slate-500">当前字数：2,158 字 · 预计场景目标：3,000-5,000 字 · 最小生成单位：scene</p></div>
        <div className="flex gap-2"><Button onClick={() => toast.success("已创建 scene generation_job（mock）")}><Sparkles className="size-4" /> 生成当前场景</Button><Button variant="secondary" onClick={() => toast.info("将基于审稿问题执行局部重写（mock）")}>局部重写</Button></div>
      </div>
      <div className="grid min-h-[720px] gap-4 xl:grid-cols-[280px_minmax(520px,1fr)_340px]">
        <Card className="overflow-hidden">
          <CardHeader><CardTitle>章节 / 场景</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <p className="font-bold text-slate-950">卷一 · 迷雾之城 <span className="text-xs text-slate-500">共 18 章</span></p>
            {chapters.map((chapter) => (
              <div key={chapter.id} className="rounded-2xl border border-slate-200 p-3">
                <div className="flex items-center justify-between"><p className="text-sm font-bold text-slate-950">第{chapter.chapterIndex}章 {chapter.title}</p><StatusBadge status={chapter.status} /></div>
                {chapter.id === "ch_13" ? <div className="mt-3 space-y-2">{scenes.map((scene) => <div key={scene.id} className={`flex items-center justify-between rounded-xl px-3 py-2 text-sm ${scene.id === "scene_13_2" ? "bg-indigo-50 text-indigo-700" : "bg-slate-50 text-slate-600"}`}><span>场景{scene.sceneIndex}：{scene.title}</span><StatusBadge status={scene.status} /></div>)}</div> : null}
              </div>
            ))}
            <Button variant="secondary" className="w-full">+ 新建章节 / 场景</Button>
          </CardContent>
        </Card>
        <div className="space-y-4"><EditorMock /><Card><CardHeader><CardTitle>生成任务日志（当前 Workflow）</CardTitle></CardHeader><CardContent><WorkflowSteps steps={workflowSteps} /><div className="mt-4 grid gap-3 text-sm md:grid-cols-4"><span>模型：gpt-4o</span><span>温度：0.75</span><span>上下文长度：128k</span><span>Token 使用：4,532</span></div></CardContent></Card></div>
        <Card>
          <CardHeader><CardTitle>Context Builder</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2">{tabs.map((tab) => <button key={tab} type="button" onClick={() => setActiveTab(tab)} className={`rounded-xl px-3 py-2 text-sm font-bold ${activeTab === tab ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-600"}`}>{tab}</button>)}</div>
            {activeTab === "记忆" ? <InspectorBlock title="前文摘要" items={["陆沉舟和苏晚在档案馆发现了通往地下库房的密道。", "禁阅索引的下级索引指向地下库房入口。"]} /> : null}
            {activeTab === "人物" ? <InspectorBlock title="人物状态" items={characters.slice(0, 2).map((c) => `${c.name}：${c.currentGoal}`)} /> : null}
            {activeTab === "世界观" ? <InspectorBlock title="世界观规则" items={worldItems.slice(0, 3).map((w) => `${w.name}：${w.summary}`)} /> : null}
            {activeTab === "审稿" ? <InspectorBlock title="审稿提醒" items={["人物行为合理性：苏晚判断过于果断，建议增加犹豫描写。", "场景描写强度：环境氛围可进一步强化。"]} /> : null}
            <Card className="bg-slate-50"><CardContent><p className="font-bold text-slate-950">Prompt 预览</p><p className="mt-2 text-sm leading-6 text-slate-500">将合并 Story Bible、人物状态、世界观召回、前文摘要与审稿约束后，交由 ModelGateway.generate_text(...)。</p></CardContent></Card>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function InspectorBlock({ title, items }: { title: string; items: string[] }) {
  return <div className="rounded-2xl border border-slate-200 p-4"><p className="font-bold text-slate-950">{title}</p><ul className="mt-3 space-y-2 text-sm leading-6 text-slate-600">{items.map((item) => <li key={item}>• {item}</li>)}</ul></div>;
}

export function JobsPage({ projectId }: { projectId: string }) {
  const [rows, setRows] = useState<GenerationJob[]>(jobs);
  const cancelJob = (id: string) => { setRows((current) => current.map((job) => job.id === id ? { ...job, status: "cancelled", progress: Math.min(job.progress, 90), releasedQuota: job.reservedQuota - job.consumedQuota } : job)); toast.warning("任务已取消，未消耗额度已释放（mock）"); };
  const retryJob = (id: string) => { setRows((current) => current.map((job) => job.id === id ? { ...job, status: "queued", progress: 0, currentStep: "等待队列" } : job)); toast.success("失败任务已重新入队（mock）"); };
  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <div className="grid gap-4 lg:grid-cols-4">
        <StatJob label="队列中" value={rows.filter((j) => j.status === "queued").length} icon={TimerReset} />
        <StatJob label="运行中" value={rows.filter((j) => j.status === "running").length} icon={RefreshCw} />
        <StatJob label="已失败" value={rows.filter((j) => j.status === "failed").length} icon={XCircle} />
        <StatJob label="已完成" value={rows.filter((j) => j.status === "succeeded").length} icon={CheckCircle2} />
      </div>
      <Card>
        <CardHeader><CardTitle>当前 Workflow 详情</CardTitle></CardHeader>
        <CardContent><WorkflowSteps steps={workflowSteps} /><div className="mt-4 rounded-2xl bg-indigo-50 p-4 text-sm text-indigo-700">任务必须经过 Auth Check → Tenant Check → Permission Check → Entitlement Check → Quota Reservation → Generation Job Creation → Workflow Start。</div></CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>任务队列表格</CardTitle></CardHeader>
        <CardContent>
          <DataTable
            rows={rows}
            columns={[
              { key: "title", header: "任务", render: (row) => <div><p className="font-bold text-slate-950">{row.title}</p><p className="text-xs text-slate-500">{row.workflowRunId}</p></div> },
              { key: "type", header: "类型", render: (row) => row.taskType },
              { key: "queue", header: "队列", render: (row) => <Badge tone="violet">{row.queue}</Badge> },
              { key: "status", header: "状态", render: (row) => <StatusBadge status={row.status} /> },
              { key: "quota", header: "额度", render: (row) => <div className="text-xs text-slate-500">预留 {row.reservedQuota}<br />结算 {row.consumedQuota}<br />释放 {row.releasedQuota}</div> },
              { key: "progress", header: "进度", render: (row) => <div className="min-w-36"><ProgressBar value={row.progress} /><p className="mt-1 text-xs text-slate-500">{row.progress}% · {row.currentStep}</p></div> },
              { key: "actions", header: "操作", render: (row) => <div className="flex gap-2">{row.status === "running" ? <Button size="sm" variant="danger" onClick={() => cancelJob(row.id)}>取消任务</Button> : null}{row.status === "failed" ? <Button size="sm" onClick={() => retryJob(row.id)}>重试</Button> : null}<Button size="sm" variant="ghost" onClick={() => toast.info("完整日志为 mock drawer")}>日志</Button></div> },
            ]}
          />
        </CardContent>
      </Card>
      <div className="grid gap-4 xl:grid-cols-[0.7fr_1.3fr]">
        <Card><CardHeader><CardTitle>额度结算卡片</CardTitle></CardHeader><CardContent className="space-y-4"><QuotaProgress used={quotas[0].usedValue} reserved={quotas[0].reservedValue} limit={quotas[0].limitValue} />{reservations.map((reservation) => <div key={reservation.id} className="rounded-2xl bg-slate-50 p-3 text-sm text-slate-600">{reservation.generationJobId} · {reservation.status} · reserved {reservation.reservedAmount} / consumed {reservation.consumedAmount}</div>)}</CardContent></Card>
        <Card><CardHeader><CardTitle>模型调用日志摘要</CardTitle></CardHeader><CardContent><ModelCallTable rows={modelCalls.slice(0, 3)} /></CardContent></Card>
      </div>
    </div>
  );
}

function StatJob({ label, value, icon: Icon }: { label: string; value: number; icon: typeof TimerReset }) {
  return <Card><CardContent className="flex items-center gap-4"><div className="grid size-12 place-items-center rounded-2xl bg-indigo-50 text-indigo-600"><Icon className="size-6" /></div><div><p className="text-sm text-slate-500">{label}</p><p className="text-3xl font-black text-slate-950">{value}</p></div></CardContent></Card>;
}

export function VersionsPage({ projectId }: { projectId: string }) {
  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
        <Card><CardHeader><CardTitle>版本历史</CardTitle></CardHeader><CardContent className="space-y-3">{["draft_v12", "draft_v11", "final_ch12", "review_patch_03"].map((version, index) => <div key={version} className="flex items-center justify-between rounded-2xl border border-slate-200 p-4"><div><p className="font-bold text-slate-950">{version}</p><p className="text-xs text-slate-500">{index === 0 ? "当前版本" : "可对比 / 可回滚"}</p></div><Button variant="secondary" size="sm" onClick={() => toast.info("版本对比/回滚为 mock action")}>{index === 0 ? "查看" : "对比"}</Button></div>)}</CardContent></Card>
        <Card><CardHeader><CardTitle>审稿问题</CardTitle></CardHeader><CardContent><DataTable rows={issues} columns={[{ key: "title", header: "问题", render: (row) => <div><p className="font-bold text-slate-950">{row.title}</p><p className="text-xs text-slate-500">{row.suggestion}</p></div> }, { key: "type", header: "类型", render: (row) => row.type }, { key: "severity", header: "等级", render: (row) => <Badge tone={row.severity === "high" ? "rose" : "amber"}>{row.severity}</Badge> }, { key: "status", header: "状态", render: (row) => <StatusBadge status={row.status} /> }, { key: "action", header: "操作", render: () => <Button size="sm" variant="secondary">修复建议</Button> }]} /></CardContent></Card>
      </div>
    </div>
  );
}

export function ExportPage({ projectId }: { projectId: string }) {
  const [files, setFiles] = useState<ExportFile[]>(exportsData);
  const startExport = (format: ExportFile["format"]) => {
    const next: ExportFile = { id: `exp_${Date.now()}`, organizationId: "org_personal", projectId, format, fileName: `雾都归档人_final_${format}_${Date.now()}.${format.toLowerCase()}`, source: "final_version", size: "生成中", status: "generating", createdAt: new Date().toISOString() };
    setFiles((current) => [next, ...current]);
    toast.success("已创建导出任务，来源：final 版本（mock）");
  };
  const formats: ExportFile["format"][] = ["Markdown", "TXT", "DOCX", "EPUB", "PDF"];
  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <div className="grid gap-4 md:grid-cols-5">{formats.map((format) => <Card key={format}><CardContent className="text-center"><FileArchive className="mx-auto size-9 text-indigo-600" /><h3 className="mt-3 font-black text-slate-950">{format}</h3><p className="mt-1 text-xs text-slate-500">导出来源：final 版本</p><Button className="mt-4 w-full" size="sm" onClick={() => startExport(format)}>开始导出</Button></CardContent></Card>)}</div>
      <div className="grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
        <Card><CardHeader><CardTitle>导出配置</CardTitle></CardHeader><CardContent className="space-y-4"><BibleBlock title="章节范围" text="第1章 - 第13章；默认只导出 final 版本。" /><BibleBlock title="套餐权益" text="Pro 套餐支持 DOCX / EPUB / PDF；Free 仅支持 Markdown / TXT。" /><Button variant="secondary" onClick={() => toast.info("目录预览为 mock action")}>预览目录</Button></CardContent></Card>
        <Card><CardHeader><CardTitle>最近导出文件</CardTitle></CardHeader><CardContent><DataTable rows={files} columns={[{ key: "file", header: "文件", render: (row) => <div><p className="font-bold text-slate-950">{row.fileName}</p><p className="text-xs text-slate-500">{row.source}</p></div> }, { key: "format", header: "格式", render: (row) => row.format }, { key: "status", header: "状态", render: (row) => <StatusBadge status={row.status === "ready" ? "succeeded" : row.status === "generating" ? "running" : "failed"} /> }, { key: "time", header: "时间", render: (row) => formatDateTime(row.createdAt) }, { key: "download", header: "操作", render: () => <Button size="sm" variant="secondary"><Download className="size-4" /> 下载</Button> }]} /></CardContent></Card>
      </div>
    </div>
  );
}
