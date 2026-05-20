"use client";

/**
 * 项目详情子页集合。
 *
 * 已从 mock-data 切换为真实 API（characters / chapters / scenes / world-items / exports / versions）。
 * 部分页面（写作工作台 / 故事圣经）仍含静态展示文案，作为前端骨架；后端有数据时会自动展示，
 * 否则显示空态或固定提示。
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  Boxes,
  CheckCircle2,
  Download,
  FileArchive,
  GitCompare,
  Layers3,
  Network,
  Pencil,
  Plus,
  RefreshCw,
  Settings2,
  Sparkles,
  TimerReset,
  Trash2,
  Users,
  Wand2,
  X,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { ProjectHeader } from "./project-frame";
import { useAuth } from "@/components/providers/auth-provider";
import { ActionCard } from "@/components/ui/action-card";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { ProgressBar } from "@/components/ui/progress";
import { DiffView } from "@/components/ui/diff-view";
import { SceneEditor } from "@/components/ui/scene-editor";
import { isPlatformAdmin } from "@/lib/permissions";
import {
  chaptersApi,
  charactersApi,
  continuityIssuesApi,
  exportsApi,
  jobsApi,
  plotThreadsApi,
  projectsApi,
  scenesApi,
  specApi,
  versionsApi,
  worldItemsApi,
} from "@/lib/api";
import type {
  Bible,
  BibleCharacter,
  BiblePlotThread,
  BibleWorldItem,
  CharacterPayload,
  DraftVersion,
  GenerateBiblePayload,
  GenerationJob,
  NovelSpecPayload,
  PlotThreadPayload,
  PreflightReport,
  StoryDirection,
  WorldItemPayload,
} from "@/lib/api";
import { ApiError } from "@/lib/http";
import { formatDateTime } from "@/lib/format";
import { useScopedKey } from "@/lib/use-scoped-key";

type Character = {
  id: string;
  name: string;
  role: string;
  description: string;
  motivation: string;
  secret: string;
};

type WorldItem = {
  id: string;
  type: string;
  name: string;
  description: string;
};

type Job = {
  id: string;
  project_id: string;
  job_type: string;
  status: string;
  workflow_id: string | null;
  reserved_quota: number;
  consumed_quota: number;
};

function BibleBlock({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <p className="text-sm font-black text-slate-950">{title}</p>
      <p className="mt-2 text-sm leading-6 text-slate-600">{text}</p>
    </div>
  );
}

function BibleItem({
  title,
  badge,
  text,
}: {
  title: string;
  badge?: string;
  text: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="font-bold text-slate-950">{title}</p>
        {badge ? <Badge tone="slate">{badge}</Badge> : null}
      </div>
      <p className="mt-2 text-sm leading-6 text-slate-500">{text || "—"}</p>
    </div>
  );
}

// =========== 故事圣经 ===========
type CreativePrefs = {
  // 基础：默认展开
  topic: string;
  protagonist_archetype: string;
  target_reader: string;
  story_tone: string;
  forbidden_themes: string;
  // 高级：默认收起
  reference_works: string;
  pacing: string;
  ending_lean: string;
  automation_level: string;
  audit_strictness: string;
  temperature: number;
};

const DEFAULT_PREFS: CreativePrefs = {
  topic: "",
  protagonist_archetype: "",
  target_reader: "",
  story_tone: "",
  forbidden_themes: "",
  reference_works: "",
  pacing: "",
  ending_lean: "",
  automation_level: "standard",
  audit_strictness: "standard",
  temperature: 0.7,
};

function splitTags(value: string): string[] {
  return value
    .split(/[,，;；\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function BiblePage({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isAdmin = isPlatformAdmin(user);
  const projectKey = useScopedKey("project", projectId);
  const bibleKey = useScopedKey("project", projectId, "bible");
  const charactersKey = useScopedKey("project", projectId, "characters");
  const worldItemsKey = useScopedKey("project", projectId, "world-items");
  const plotThreadsKey = useScopedKey("project", projectId, "plot-threads");
  const preflightKey = useScopedKey("project", projectId, "preflight", "generate_bible");
  const jobsKey = useScopedKey("jobs");

  const { data: bible, isPending } = useQuery({
    queryKey: bibleKey,
    queryFn: () => projectsApi.getBible(projectId),
    refetchInterval: (query) => {
      const data = query.state.data as Bible | undefined;
      const latestJob = data?.latest_job;
      const waitingForJob = latestJob?.status === "queued" || latestJob?.status === "running";
      const waitingForResult = latestJob?.status === "succeeded" && !data?.spec;
      return waitingForJob || waitingForResult ? 1500 : false;
    },
  });
  const { data: preflight } = useQuery({
    queryKey: preflightKey,
    queryFn: () => projectsApi.preflight(projectId, "generate_bible"),
  });
  const latestJob = bible?.latest_job;
  const isGenerating = latestJob?.status === "queued" || latestJob?.status === "running";

  const [prefsOpen, setPrefsOpen] = useState(false);
  const [prefsAdvanced, setPrefsAdvanced] = useState(false);
  const [defaultsExplain, setDefaultsExplain] = useState(false);
  const [prefs, setPrefs] = useState<CreativePrefs>(DEFAULT_PREFS);
  const [directionPreviewOpen, setDirectionPreviewOpen] = useState(false);
  const [specEditing, setSpecEditing] = useState(false);
  const [editChar, setEditChar] = useState<BibleCharacter | "new" | null>(null);
  const [editWorld, setEditWorld] = useState<BibleWorldItem | "new" | null>(null);
  const [editThread, setEditThread] = useState<BiblePlotThread | "new" | null>(null);

  const generate = useMutation({
    mutationFn: () => {
      const payload: GenerateBiblePayload = {
        estimate_words: preflight?.estimate_words ?? 2000,
        // 已有 spec 时按钮文案是「重新生成」，用户预期就是覆盖式重生成
        force_regenerate: Boolean(bible?.spec),
        topic: prefs.topic.trim() || undefined,
        protagonist_archetype: prefs.protagonist_archetype.trim() || undefined,
        reference_works: splitTags(prefs.reference_works),
        forbidden_themes: splitTags(prefs.forbidden_themes),
        temperature: prefs.temperature,
        target_reader: prefs.target_reader.trim() || undefined,
        story_tone: prefs.story_tone.trim() || undefined,
        pacing: prefs.pacing.trim() || undefined,
        ending_lean: prefs.ending_lean.trim() || undefined,
        automation_level: prefs.automation_level || undefined,
        audit_strictness: prefs.audit_strictness || undefined,
      };
      return projectsApi.generateBible(projectId, payload);
    },
    onSuccess: () => {
      toast.success("已提交故事圣经生成任务");
      queryClient.invalidateQueries({ queryKey: bibleKey });
      queryClient.invalidateQueries({ queryKey: projectKey });
      queryClient.invalidateQueries({ queryKey: charactersKey });
      queryClient.invalidateQueries({ queryKey: worldItemsKey });
      queryClient.invalidateQueries({ queryKey: plotThreadsKey });
      queryClient.invalidateQueries({ queryKey: preflightKey });
      queryClient.invalidateQueries({ queryKey: jobsKey });
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "提交失败");
    },
  });

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: bibleKey });
    queryClient.invalidateQueries({ queryKey: charactersKey });
    queryClient.invalidateQueries({ queryKey: worldItemsKey });
    queryClient.invalidateQueries({ queryKey: plotThreadsKey });
  };

  const spec = bible?.spec;
  const characters = bible?.characters ?? [];
  const worldItems = bible?.world_items ?? [];
  const plotThreads = bible?.plot_threads ?? [];

  const canGenerate = preflight?.can_generate !== false;
  const disableGenerate = generate.isPending || isGenerating || !canGenerate;

  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />

      <ProjectStageCard
        projectId={projectId}
        projectStatus={preflight?.project_status ?? bible?.project_status ?? "created"}
        hasSpec={Boolean(spec)}
        characterCount={characters.length}
        worldItemCount={worldItems.length}
        plotThreadCount={plotThreads.length}
      />

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>故事启动中心 Story Setup Center</CardTitle>
            <p className="mt-1 text-sm text-slate-500">
              系统的第一步是生成故事圣经。可选择「预览创作方向」先确认大方向，或直接填「创作偏好」启动生成。
            </p>
          </div>
          <div className="flex items-center gap-2">
            {latestJob ? <StatusBadge status={latestJob.status as never} /> : null}
            <Badge tone={spec ? "blue" : "slate"}>{spec ? "已生成" : "未生成"}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          {preflight ? <PreflightCard report={preflight} /> : null}

          <WillGenerateList />

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-slate-50 p-4">
            <div>
              <p className="font-bold text-slate-950">本次生成</p>
              <p className="text-sm text-slate-500">
                提交后会预留额度，调用模型，完成后自动展示结果。
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="ghost" onClick={() => setDirectionPreviewOpen(true)}>
                <Wand2 className="size-4" /> 预览创作方向
              </Button>
              <Button variant="ghost" onClick={() => setPrefsOpen((v) => !v)}>
                <Settings2 className="size-4" /> {prefsOpen ? "收起创作偏好" : "创作偏好"}
              </Button>
              <Button onClick={() => generate.mutate()} disabled={disableGenerate}>
                {isGenerating ? <RefreshCw className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                {spec ? "重新生成" : "启动生成"}
              </Button>
            </div>
          </div>

          {prefsOpen ? (
            <CreativePrefsCard
              prefs={prefs}
              onChange={setPrefs}
              advanced={prefsAdvanced}
              onToggleAdvanced={() => setPrefsAdvanced((v) => !v)}
              defaultsExplain={defaultsExplain}
              onToggleDefaultsExplain={() => setDefaultsExplain((v) => !v)}
            />
          ) : null}

          {latestJob ? (
            <div className="grid gap-3 md:grid-cols-3">
              <BibleBlock title="任务类型" text={taskTypeLabel(latestJob.job_type)} />
              <BibleBlock
                title="本次额度"
                text={
                  latestJob.consumed_quota > 0
                    ? `预估 ${latestJob.reserved_quota} 字 · 实际 ${latestJob.consumed_quota} 字`
                    : `预估 ${latestJob.reserved_quota} 字 · 等待结算`
                }
              />
              <BibleBlock
                title="任务状态"
                text={latestJob.status === "succeeded" ? "已完成" : latestJob.status}
              />
              {isAdmin && latestJob.workflow_id ? (
                <p className="md:col-span-3 truncate text-xs text-slate-400">
                  Workflow ID（仅管理员可见）：{latestJob.workflow_id}
                </p>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {isPending ? (
        <Card>
          <CardContent className="p-12 text-center text-sm text-slate-500">正在读取故事圣经...</CardContent>
        </Card>
      ) : !spec ? (
        <Card>
          <CardContent className="p-12 text-center">
            <p className="text-base font-bold text-slate-950">还没有故事圣经</p>
            <p className="mt-2 text-sm text-slate-500">点击上方按钮后，这里会显示项目核心设定。</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>核心设定</CardTitle>
              <div className="flex items-center gap-2">
                <Badge tone="violet">{spec.genre || "未分类"}</Badge>
                <Button size="sm" variant="ghost" onClick={() => setSpecEditing(true)}>
                  <Pencil className="size-3.5" /> 编辑
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <BibleBlock title="Premise" text={spec.premise || "—"} />
                <BibleBlock title="Theme" text={spec.theme || "—"} />
                <BibleBlock title="Tone" text={spec.tone || "—"} />
                <BibleBlock title="POV" text={spec.narrative_pov || "—"} />
              </div>
              <BibleBlock title="Style Guide" text={spec.style_guide || "—"} />
              <div className="grid gap-3 md:grid-cols-2">
                {spec.constraints.map((item) => (
                  <BibleItem key={item} title="约束 / 规则" text={item} />
                ))}
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>主要人物</CardTitle>
                <Button size="sm" variant="ghost" onClick={() => setEditChar("new")}>
                  <Plus className="size-3.5" /> 新增
                </Button>
              </CardHeader>
              <CardContent className="grid gap-3 md:grid-cols-2">
                {characters.length === 0 ? (
                  <p className="text-sm text-slate-500">暂无人物。</p>
                ) : (
                  characters.map((character: BibleCharacter) => (
                    <EditableItem
                      key={character.id}
                      title={character.name}
                      badge={character.role}
                      text={[character.description, character.motivation, character.arc]
                        .filter(Boolean)
                        .join(" / ")}
                      onEdit={() => setEditChar(character)}
                    />
                  ))
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>剧情线</CardTitle>
                <Button size="sm" variant="ghost" onClick={() => setEditThread("new")}>
                  <Plus className="size-3.5" /> 新增
                </Button>
              </CardHeader>
              <CardContent className="space-y-3">
                {plotThreads.length === 0 ? (
                  <p className="text-sm text-slate-500">暂无剧情线。</p>
                ) : (
                  plotThreads.map((thread: BiblePlotThread) => (
                    <EditableItem
                      key={thread.id}
                      title={thread.title}
                      badge={`${thread.thread_type} · ${thread.status}`}
                      text={thread.description}
                      onEdit={() => setEditThread(thread)}
                    />
                  ))
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>世界观条目</CardTitle>
              <Button size="sm" variant="ghost" onClick={() => setEditWorld("new")}>
                <Plus className="size-3.5" /> 新增
              </Button>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {worldItems.length === 0 ? (
                <p className="text-sm text-slate-500">暂无世界观条目。</p>
              ) : (
                worldItems.map((item: BibleWorldItem) => (
                  <EditableItem
                    key={item.id}
                    title={item.name}
                    badge={item.is_hard_rule ? "硬规则" : item.importance}
                    text={item.description}
                    onEdit={() => setEditWorld(item)}
                  />
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
              <div className="flex items-center gap-3">
                <div className="rounded-2xl bg-indigo-50 p-2 text-indigo-600">
                  <Layers3 className="size-5" />
                </div>
                <div>
                  <p className="font-bold text-slate-950">
                    下一步：{preflight?.next_action?.label ?? "生成章节大纲"}
                  </p>
                  <p className="text-sm text-slate-500">
                    根据故事圣经规划三幕推进，逐章产出标题、目标、冲突、钩子。
                  </p>
                </div>
              </div>
              <Link
                href={`/studio/projects/${projectId}${preflight?.next_action?.href_suffix ?? "/outline"}`}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-800 transition hover:bg-slate-50"
              >
                前往 <Sparkles className="size-4" />
              </Link>
            </CardContent>
          </Card>
        </>
      )}

      {/* 编辑 / 预览弹窗 */}
      {directionPreviewOpen ? (
        <DirectionPreviewDialog
          projectId={projectId}
          prefs={prefs}
          onClose={() => setDirectionPreviewOpen(false)}
          onPick={(d) => {
            setPrefs((p) => ({ ...p, topic: d.summary }));
            setPrefsOpen(true);
            setDirectionPreviewOpen(false);
            toast.success(`已选定方向：${d.name}`);
          }}
        />
      ) : null}
      {specEditing && spec ? (
        <SpecEditDialog
          projectId={projectId}
          spec={spec}
          onClose={() => setSpecEditing(false)}
          onSaved={() => {
            setSpecEditing(false);
            invalidateAll();
          }}
        />
      ) : null}
      {editChar ? (
        <CharacterEditDialog
          projectId={projectId}
          character={editChar === "new" ? null : editChar}
          onClose={() => setEditChar(null)}
          onSaved={() => {
            setEditChar(null);
            invalidateAll();
          }}
        />
      ) : null}
      {editWorld ? (
        <WorldItemEditDialog
          projectId={projectId}
          item={editWorld === "new" ? null : editWorld}
          onClose={() => setEditWorld(null)}
          onSaved={() => {
            setEditWorld(null);
            invalidateAll();
          }}
        />
      ) : null}
      {editThread ? (
        <PlotThreadEditDialog
          projectId={projectId}
          thread={editThread === "new" ? null : editThread}
          onClose={() => setEditThread(null)}
          onSaved={() => {
            setEditThread(null);
            invalidateAll();
          }}
        />
      ) : null}
    </div>
  );
}

function taskTypeLabel(jobType: string): string {
  const m: Record<string, string> = {
    generate_bible: "故事圣经生成",
    generate_outline: "章节大纲生成",
    generate_scene_plan: "场景拆分",
    write_scene: "场景正文写作",
    audit_scene: "审稿",
    rewrite_scene: "重写",
    full_novel: "全书生成",
  };
  return m[jobType] ?? jobType;
}

/** 项目阶段卡片：展示当前里程碑 + 推荐下一步。 */
function ProjectStageCard({
  projectId,
  projectStatus,
  hasSpec,
  characterCount,
  worldItemCount,
  plotThreadCount,
}: {
  projectId: string;
  projectStatus: string;
  hasSpec: boolean;
  characterCount: number;
  worldItemCount: number;
  plotThreadCount: number;
}) {
  // 里程碑顺序：created → bible → outline → scenes → drafting → completed
  const milestones = [
    { key: "bible", label: "故事圣经", done: hasSpec },
    {
      key: "outline",
      label: "章节大纲",
      done: ["outlined", "scenes_planning", "scenes_planned", "drafting", "completed"].includes(
        projectStatus,
      ),
    },
    {
      key: "scenes",
      label: "场景计划",
      done: ["scenes_planned", "drafting", "completed"].includes(projectStatus),
    },
    {
      key: "drafting",
      label: "章节正文",
      done: ["drafting", "completed"].includes(projectStatus),
    },
    { key: "completed", label: "全书完结", done: projectStatus === "completed" },
  ];
  return (
    <Card>
      <CardContent className="space-y-4 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm text-slate-500">当前阶段</p>
            <p className="mt-1 text-lg font-black text-slate-950">
              {projectStatus} {hasSpec ? "·  圣经就绪" : ""}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm text-slate-600">
            <span>人物 {characterCount}</span>
            <span>世界观 {worldItemCount}</span>
            <span>剧情线 {plotThreadCount}</span>
          </div>
        </div>
        <div className="flex items-center gap-2 overflow-x-auto">
          {milestones.map((m, i) => (
            <div key={m.key} className="flex items-center gap-2">
              <div
                className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-bold ${
                  m.done
                    ? "bg-emerald-100 text-emerald-800"
                    : "bg-slate-100 text-slate-500"
                }`}
              >
                {m.done ? <CheckCircle2 className="size-3.5" /> : <TimerReset className="size-3.5" />}
                {m.label}
              </div>
              {i < milestones.length - 1 ? (
                <span className="text-slate-300">›</span>
              ) : null}
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-400">
          项目 ID: {projectId}
        </p>
      </CardContent>
    </Card>
  );
}

/** 生成前检查卡片：套餐 / 额度 / 风险。 */
function PreflightCard({ report }: { report: PreflightReport }) {
  const remaining = report.quota_available;
  const limit = report.quota_limit;
  const pct = limit > 0 ? Math.min(100, Math.round(((limit - remaining) / limit) * 100)) : 0;
  return (
    <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-bold text-slate-950">生成前检查</p>
        <div className="flex items-center gap-2 text-xs">
          <Badge tone="violet">{report.plan_code}</Badge>
          <span className="text-slate-500">
            剩余 {remaining.toLocaleString()} / {limit.toLocaleString()} 字
          </span>
        </div>
      </div>
      <ProgressBar value={pct} tone={remaining >= report.estimate_words ? "green" : "orange"} />
      <ul className="space-y-2 text-sm">
        {report.checks.map((c, i) => (
          <li key={i} className="flex items-start gap-2">
            {c.level === "ok" ? (
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" />
            ) : c.level === "warn" ? (
              <TimerReset className="mt-0.5 size-4 shrink-0 text-amber-600" />
            ) : (
              <XCircle className="mt-0.5 size-4 shrink-0 text-rose-600" />
            )}
            <div>
              <p className="font-semibold text-slate-800">{c.label}</p>
              {c.detail ? <p className="text-slate-500">{c.detail}</p> : null}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** 列出本次生成会产出什么，给用户预期感。 */
function WillGenerateList() {
  const items = [
    "故事前提（Premise）",
    "核心主题（Theme）",
    "主线冲突 / 张力源",
    "主角与关键人物原型",
    "世界观基础规则",
    "剧情线 / 主要伏笔",
    "文风规则与叙事视角",
    "禁忌与硬约束",
  ];
  return (
    <div className="rounded-2xl border border-emerald-100 bg-emerald-50/40 p-4">
      <p className="text-sm font-bold text-emerald-900">本次将生成</p>
      <ul className="mt-2 grid gap-1.5 text-sm text-emerald-900/80 md:grid-cols-2">
        {items.map((it) => (
          <li key={it} className="flex items-center gap-2">
            <CheckCircle2 className="size-3.5" /> {it}
          </li>
        ))}
      </ul>
    </div>
  );
}

function DirectionPreviewDialog({
  projectId,
  prefs,
  onClose,
  onPick,
}: {
  projectId: string;
  prefs: CreativePrefs;
  onClose: () => void;
  onPick: (d: StoryDirection) => void;
}) {
  const { data, isPending, isError } = useQuery({
    queryKey: ["preview-directions", projectId, prefs.topic, prefs.protagonist_archetype],
    queryFn: () =>
      projectsApi.previewDirections(projectId, {
        topic: prefs.topic || undefined,
        protagonist_archetype: prefs.protagonist_archetype || undefined,
        reference_works: splitTags(prefs.reference_works),
        forbidden_themes: splitTags(prefs.forbidden_themes),
      }),
  });
  return (
    <Modal title="预览 3 个创作方向" onClose={onClose}>
      <p className="mb-3 text-sm text-slate-500">
        从下面 3 个方向中挑一个最贴近你的预期，点「选用」后会自动回填到「创作意图」字段。
      </p>
      {isPending ? (
        <p className="py-6 text-center text-sm text-slate-500">加载中…</p>
      ) : isError || !data ? (
        <p className="py-6 text-center text-sm text-rose-500">加载失败</p>
      ) : (
        <div className="space-y-3">
          {data.directions.map((d) => (
            <div
              key={d.name}
              className={`rounded-2xl border p-4 ${
                d.recommended ? "border-indigo-300 bg-indigo-50/40" : "border-slate-200"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <p className="font-bold text-slate-950">
                  {d.name} {d.recommended ? <Badge tone="violet">推荐</Badge> : null}
                </p>
                <Button size="sm" onClick={() => onPick(d)}>
                  选用
                </Button>
              </div>
              <p className="mt-2 text-sm text-slate-700">{d.summary}</p>
              {d.selling_points.length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {d.selling_points.map((sp) => (
                    <Badge key={sp} tone="green">
                      {sp}
                    </Badge>
                  ))}
                </div>
              ) : null}
              {d.risk ? <p className="mt-2 text-xs text-amber-700">⚠ {d.risk}</p> : null}
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}

function CreativePrefsCard({
  prefs,
  onChange,
  advanced,
  onToggleAdvanced,
  defaultsExplain,
  onToggleDefaultsExplain,
}: {
  prefs: CreativePrefs;
  onChange: (next: CreativePrefs) => void;
  advanced: boolean;
  onToggleAdvanced: () => void;
  defaultsExplain: boolean;
  onToggleDefaultsExplain: () => void;
}) {
  const update = <K extends keyof CreativePrefs>(key: K, value: CreativePrefs[K]) => {
    onChange({ ...prefs, [key]: value });
  };
  return (
    <div className="space-y-4 rounded-2xl border border-indigo-100 bg-indigo-50/40 p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-bold text-indigo-900">创作偏好（可选，全部留空走默认）</p>
        <Button size="sm" variant="ghost" onClick={onToggleDefaultsExplain}>
          {defaultsExplain ? "隐藏默认说明" : "查看默认策略"}
        </Button>
      </div>
      {defaultsExplain ? (
        <div className="rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-600 leading-6">
          <p className="font-bold text-slate-700">字段全部留空时，系统会按以下默认策略推断：</p>
          <ul className="ml-4 mt-1 list-disc">
            <li>从项目标题 / 类型 / 目标章节数推断故事类型</li>
            <li>主角原型基于通用文学范式，偏内敛 + 有明确动机</li>
            <li>避免血腥、政治隐喻、色情等高风险内容</li>
            <li>温度默认 0.7，平衡稳定与发挥</li>
            <li>自动化默认「标准」：关键里程碑（圣经 / 大纲 / 前 3 章）会要求确认</li>
            <li>审稿默认「标准」严格度</li>
          </ul>
        </div>
      ) : null}

      {/* 基础偏好 */}
      <label className="block text-sm font-semibold text-slate-700">
        创作意图 / 主题
        <textarea
          rows={2}
          value={prefs.topic}
          onChange={(e) => update("topic", e.target.value)}
          placeholder="比如：在记忆可以被买卖的城市里，一名档案修复师追查妹妹失踪案。"
          className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
        />
      </label>
      <label className="block text-sm font-semibold text-slate-700">
        主角原型 / 期望
        <textarea
          rows={2}
          value={prefs.protagonist_archetype}
          onChange={(e) => update("protagonist_archetype", e.target.value)}
          placeholder="比如：失忆的天才档案管理员，内敛、对真相有偏执的执念。"
          className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
        />
      </label>
      <div className="grid gap-4 md:grid-cols-2">
        <label className="block text-sm font-semibold text-slate-700">
          目标读者
          <select
            value={prefs.target_reader}
            onChange={(e) => update("target_reader", e.target.value)}
            className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
          >
            <option value="">默认</option>
            <option value="男频读者">男频读者</option>
            <option value="女频读者">女频读者</option>
            <option value="青少年">青少年</option>
            <option value="成人悬疑读者">成人悬疑读者</option>
            <option value="轻小说读者">轻小说读者</option>
          </select>
        </label>
        <label className="block text-sm font-semibold text-slate-700">
          故事基调
          <select
            value={prefs.story_tone}
            onChange={(e) => update("story_tone", e.target.value)}
            className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
          >
            <option value="">默认</option>
            <option value="轻松">轻松</option>
            <option value="治愈">治愈</option>
            <option value="热血">热血</option>
            <option value="悬疑">悬疑</option>
            <option value="黑暗">黑暗</option>
            <option value="史诗">史诗</option>
            <option value="压抑">压抑</option>
          </select>
        </label>
      </div>
      <label className="block text-sm font-semibold text-slate-700">
        禁忌主题（逗号分隔，绝对不要出现）
        <input
          value={prefs.forbidden_themes}
          onChange={(e) => update("forbidden_themes", e.target.value)}
          placeholder="血腥, 政治隐喻"
          className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
        />
      </label>

      <div className="flex items-center justify-between">
        <p className="text-xs font-bold text-slate-500">高级偏好</p>
        <Button size="sm" variant="ghost" onClick={onToggleAdvanced}>
          {advanced ? "收起" : "展开"}
        </Button>
      </div>
      {advanced ? (
        <div className="space-y-4">
          <label className="block text-sm font-semibold text-slate-700">
            参考作品（逗号分隔，仅做风格参考）
            <input
              value={prefs.reference_works}
              onChange={(e) => update("reference_works", e.target.value)}
              placeholder="盗梦空间, 银翼杀手"
              className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
            />
          </label>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="block text-sm font-semibold text-slate-700">
              节奏偏好
              <select
                value={prefs.pacing}
                onChange={(e) => update("pacing", e.target.value)}
                className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
              >
                <option value="">默认</option>
                <option value="快节奏强钩子">快节奏强钩子</option>
                <option value="中等节奏">中等节奏</option>
                <option value="慢热铺垫">慢热铺垫</option>
              </select>
            </label>
            <label className="block text-sm font-semibold text-slate-700">
              结局倾向
              <select
                value={prefs.ending_lean}
                onChange={(e) => update("ending_lean", e.target.value)}
                className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
              >
                <option value="">默认</option>
                <option value="开放式">开放式</option>
                <option value="圆满">圆满</option>
                <option value="悲剧">悲剧</option>
                <option value="反转">反转</option>
                <option value="系列续作">系列续作</option>
              </select>
            </label>
            <label className="block text-sm font-semibold text-slate-700">
              自动化程度
              <select
                value={prefs.automation_level}
                onChange={(e) => update("automation_level", e.target.value)}
                className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
              >
                <option value="cautious">谨慎 · 每步都确认</option>
                <option value="standard">标准 · 关键节点确认</option>
                <option value="auto">全自动 · 系统自动推进</option>
              </select>
            </label>
            <label className="block text-sm font-semibold text-slate-700">
              审稿严格度
              <select
                value={prefs.audit_strictness}
                onChange={(e) => update("audit_strictness", e.target.value)}
                className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
              >
                <option value="loose">宽松</option>
                <option value="standard">标准</option>
                <option value="strict">严格</option>
              </select>
            </label>
          </div>
          <label className="block text-sm font-semibold text-slate-700">
            创作温度（0 = 保守稳定，1.5 = 高发挥）：{prefs.temperature.toFixed(2)}
            <input
              type="range"
              min={0}
              max={1.5}
              step={0.05}
              value={prefs.temperature}
              onChange={(e) => update("temperature", Number(e.target.value))}
              className="mt-2 w-full"
            />
          </label>
        </div>
      ) : null}
    </div>
  );
}

function EditableItem({
  title,
  badge,
  text,
  onEdit,
}: {
  title: string;
  badge?: string;
  text: string;
  onEdit: () => void;
}) {
  return (
    <div className="group relative rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="font-bold text-slate-950">{title}</p>
        <div className="flex items-center gap-2">
          {badge ? <Badge tone="slate">{badge}</Badge> : null}
          <button
            type="button"
            onClick={onEdit}
            className="rounded-md p-1 text-slate-400 opacity-0 transition group-hover:opacity-100 hover:bg-slate-100 hover:text-slate-700"
            aria-label="编辑"
          >
            <Pencil className="size-3.5" />
          </button>
        </div>
      </div>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-500">{text || "—"}</p>
    </div>
  );
}

function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-black text-slate-950">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-slate-500 hover:bg-slate-100"
            aria-label="关闭"
          >
            <X className="size-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
  rows,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
  placeholder?: string;
}) {
  return (
    <label className="block text-sm font-semibold text-slate-700">
      {label}
      {rows ? (
        <textarea
          rows={rows}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
        />
      ) : (
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
        />
      )}
    </label>
  );
}

function ListField({
  label,
  values,
  onChange,
  placeholder,
}: {
  label: string;
  values: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
}) {
  return (
    <TextField
      label={`${label}（一行一条）`}
      rows={3}
      value={values.join("\n")}
      onChange={(v) => onChange(v.split("\n").map((s) => s.trim()).filter(Boolean))}
      placeholder={placeholder}
    />
  );
}

function SpecEditDialog({
  projectId,
  spec,
  onClose,
  onSaved,
}: {
  projectId: string;
  spec: NonNullable<Bible["spec"]>;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<NovelSpecPayload>({
    premise: spec.premise,
    theme: spec.theme,
    genre: spec.genre,
    tone: spec.tone,
    target_reader: spec.target_reader,
    narrative_pov: spec.narrative_pov,
    style_guide: spec.style_guide,
    constraints: spec.constraints,
    continuity_rules: [],
  });
  const save = useMutation({
    mutationFn: () => specApi.upsert(projectId, form),
    onSuccess: () => {
      toast.success("核心设定已更新");
      onSaved();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "保存失败"),
  });
  const set = <K extends keyof NovelSpecPayload>(k: K, v: NovelSpecPayload[K]) =>
    setForm((p) => ({ ...p, [k]: v }));
  return (
    <Modal title="编辑核心设定" onClose={onClose}>
      <div className="space-y-3">
        <TextField label="Premise" rows={3} value={form.premise ?? ""} onChange={(v) => set("premise", v)} />
        <div className="grid gap-3 md:grid-cols-2">
          <TextField label="Theme" value={form.theme ?? ""} onChange={(v) => set("theme", v)} />
          <TextField label="Genre" value={form.genre ?? ""} onChange={(v) => set("genre", v)} />
          <TextField label="Tone" value={form.tone ?? ""} onChange={(v) => set("tone", v)} />
          <TextField
            label="POV"
            value={form.narrative_pov ?? ""}
            onChange={(v) => set("narrative_pov", v)}
          />
          <TextField
            label="Target Reader"
            value={form.target_reader ?? ""}
            onChange={(v) => set("target_reader", v)}
          />
        </div>
        <TextField
          label="Style Guide"
          rows={3}
          value={form.style_guide ?? ""}
          onChange={(v) => set("style_guide", v)}
        />
        <ListField
          label="约束 / 规则"
          values={form.constraints ?? []}
          onChange={(v) => set("constraints", v)}
        />
        <ListField
          label="连贯性规则"
          values={form.continuity_rules ?? []}
          onChange={(v) => set("continuity_rules", v)}
        />
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? "保存中…" : "保存"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function CharacterEditDialog({
  projectId,
  character,
  onClose,
  onSaved,
}: {
  projectId: string;
  character: BibleCharacter | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<CharacterPayload>({
    name: character?.name ?? "",
    role: character?.role ?? "",
    description: character?.description ?? "",
    motivation: character?.motivation ?? "",
    arc: character?.arc ?? "",
    secret: "",
    personality: "",
  });
  const save = useMutation({
    mutationFn: () =>
      character
        ? charactersApi.update(projectId, character.id, form)
        : charactersApi.create(projectId, form),
    onSuccess: () => {
      toast.success(character ? "人物已更新" : "人物已创建");
      onSaved();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "保存失败"),
  });
  const remove = useMutation({
    mutationFn: () => {
      if (!character) throw new Error("no character");
      return charactersApi.remove(projectId, character.id);
    },
    onSuccess: () => {
      toast.success("人物已删除");
      onSaved();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "删除失败"),
  });
  const set = <K extends keyof CharacterPayload>(k: K, v: CharacterPayload[K]) =>
    setForm((p) => ({ ...p, [k]: v }));
  return (
    <Modal title={character ? "编辑人物" : "新增人物"} onClose={onClose}>
      <div className="space-y-3">
        <div className="grid gap-3 md:grid-cols-2">
          <TextField label="姓名" value={form.name} onChange={(v) => set("name", v)} />
          <TextField label="定位（protagonist / antagonist / ...）" value={form.role ?? ""} onChange={(v) => set("role", v)} />
        </div>
        <TextField label="外貌 / 描写" rows={3} value={form.description ?? ""} onChange={(v) => set("description", v)} />
        <TextField label="动机" rows={2} value={form.motivation ?? ""} onChange={(v) => set("motivation", v)} />
        <TextField label="人物弧光" rows={2} value={form.arc ?? ""} onChange={(v) => set("arc", v)} />
        <div className="flex justify-between gap-2 pt-2">
          {character ? (
            <Button
              variant="ghost"
              onClick={() => {
                if (window.confirm(`确认删除人物「${character.name}」？`)) remove.mutate();
              }}
              disabled={remove.isPending}
              className="text-red-600 hover:bg-red-50"
            >
              <Trash2 className="size-4" /> 删除
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>
              取消
            </Button>
            <Button onClick={() => save.mutate()} disabled={save.isPending || !form.name.trim()}>
              {save.isPending ? "保存中…" : "保存"}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

function WorldItemEditDialog({
  projectId,
  item,
  onClose,
  onSaved,
}: {
  projectId: string;
  item: BibleWorldItem | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<WorldItemPayload>({
    type: item?.type ?? "rule",
    name: item?.name ?? "",
    description: item?.description ?? "",
    importance: item?.importance ?? "medium",
    is_hard_rule: item?.is_hard_rule ?? false,
  });
  const save = useMutation({
    mutationFn: () =>
      item
        ? worldItemsApi.update(projectId, item.id, form)
        : worldItemsApi.create(projectId, form),
    onSuccess: () => {
      toast.success(item ? "世界观条目已更新" : "已创建");
      onSaved();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "保存失败"),
  });
  const remove = useMutation({
    mutationFn: () => {
      if (!item) throw new Error("no item");
      return worldItemsApi.remove(projectId, item.id);
    },
    onSuccess: () => {
      toast.success("已删除");
      onSaved();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "删��失败"),
  });
  const set = <K extends keyof WorldItemPayload>(k: K, v: WorldItemPayload[K]) =>
    setForm((p) => ({ ...p, [k]: v }));
  return (
    <Modal title={item ? "编辑世界观条目" : "新增世界观条目"} onClose={onClose}>
      <div className="space-y-3">
        <div className="grid gap-3 md:grid-cols-2">
          <TextField label="类型（rule / location / faction ...）" value={form.type} onChange={(v) => set("type", v)} />
          <TextField label="名称" value={form.name} onChange={(v) => set("name", v)} />
        </div>
        <TextField label="描述" rows={5} value={form.description ?? ""} onChange={(v) => set("description", v)} />
        <div className="grid gap-3 md:grid-cols-2">
          <label className="block text-sm font-semibold text-slate-700">
            重要性
            <select
              value={form.importance ?? "medium"}
              onChange={(e) => set("importance", e.target.value)}
              className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
            >
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
            </select>
          </label>
          <label className="mt-6 flex items-center gap-2 text-sm font-semibold text-slate-700">
            <input
              type="checkbox"
              checked={form.is_hard_rule ?? false}
              onChange={(e) => set("is_hard_rule", e.target.checked)}
            />
            硬规则（违反会触发审稿）
          </label>
        </div>
        <div className="flex justify-between gap-2 pt-2">
          {item ? (
            <Button
              variant="ghost"
              onClick={() => {
                if (window.confirm(`确认删除世界观条目「${item.name}」？`)) remove.mutate();
              }}
              disabled={remove.isPending}
              className="text-red-600 hover:bg-red-50"
            >
              <Trash2 className="size-4" /> 删除
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>
              取消
            </Button>
            <Button
              onClick={() => save.mutate()}
              disabled={save.isPending || !form.name.trim() || !form.type.trim()}
            >
              {save.isPending ? "保存中…" : "保存"}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

function PlotThreadEditDialog({
  projectId,
  thread,
  onClose,
  onSaved,
}: {
  projectId: string;
  thread: BiblePlotThread | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<PlotThreadPayload>({
    title: thread?.title ?? "",
    thread_type: thread?.thread_type ?? "main",
    description: thread?.description ?? "",
    status: thread?.status ?? "open",
  });
  const save = useMutation({
    mutationFn: () =>
      thread
        ? plotThreadsApi.update(projectId, thread.id, form)
        : plotThreadsApi.create(projectId, form),
    onSuccess: () => {
      toast.success(thread ? "剧情线已更新" : "已创建");
      onSaved();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "保存失败"),
  });
  const remove = useMutation({
    mutationFn: () => {
      if (!thread) throw new Error("no thread");
      return plotThreadsApi.remove(projectId, thread.id);
    },
    onSuccess: () => {
      toast.success("已删除");
      onSaved();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "删除失败"),
  });
  const set = <K extends keyof PlotThreadPayload>(k: K, v: PlotThreadPayload[K]) =>
    setForm((p) => ({ ...p, [k]: v }));
  return (
    <Modal title={thread ? "编辑剧情线" : "新增剧情线"} onClose={onClose}>
      <div className="space-y-3">
        <TextField label="名称" value={form.title} onChange={(v) => set("title", v)} />
        <div className="grid gap-3 md:grid-cols-2">
          <label className="block text-sm font-semibold text-slate-700">
            类型
            <select
              value={form.thread_type ?? "main"}
              onChange={(e) => set("thread_type", e.target.value)}
              className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
            >
              <option value="main">main 主线</option>
              <option value="sub">sub 副线</option>
              <option value="foreshadow">foreshadow 伏笔</option>
              <option value="background">background 背景</option>
            </select>
          </label>
          <label className="block text-sm font-semibold text-slate-700">
            状态
            <select
              value={form.status ?? "open"}
              onChange={(e) => set("status", e.target.value)}
              className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
            >
              <option value="open">open 进行中</option>
              <option value="closed">closed 已闭合</option>
              <option value="paused">paused 暂停</option>
            </select>
          </label>
        </div>
        <TextField label="描述" rows={4} value={form.description ?? ""} onChange={(v) => set("description", v)} />
        <div className="flex justify-between gap-2 pt-2">
          {thread ? (
            <Button
              variant="ghost"
              onClick={() => {
                if (window.confirm(`确认删除剧情线「${thread.title}」？`)) remove.mutate();
              }}
              disabled={remove.isPending}
              className="text-red-600 hover:bg-red-50"
            >
              <Trash2 className="size-4" /> 删除
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>
              取消
            </Button>
            <Button onClick={() => save.mutate()} disabled={save.isPending || !form.title.trim()}>
              {save.isPending ? "保存中…" : "保存"}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

// =========== 人物 ===========
export function CharactersPage({ projectId }: { projectId: string }) {
  const { data: characters = [] } = useQuery({
    queryKey: useScopedKey("project", projectId, "characters"),
    queryFn: () => charactersApi.list(projectId) as Promise<Character[]>,
  });
  const [activeId, setActiveId] = useState<string | null>(null);
  const active = characters.find((c) => c.id === activeId) ?? characters[0];

  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <div className="grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
        <Card>
          <CardHeader>
            <CardTitle>人物列表</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {characters.length === 0 ? (
              <p className="py-8 text-center text-sm text-slate-500">暂无人物，去创建吧。</p>
            ) : (
              characters.map((character) => (
                <button
                  key={character.id}
                  type="button"
                  onClick={() => setActiveId(character.id)}
                  className={`w-full rounded-2xl border p-4 text-left transition ${
                    active?.id === character.id
                      ? "border-indigo-300 bg-indigo-50"
                      : "border-slate-200 hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <p className="font-bold text-slate-950">{character.name}</p>
                    <Badge tone="violet">{character.role || "未定义"}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-slate-500">
                    {character.description?.slice(0, 80) || "—"}
                  </p>
                </button>
              ))
            )}
          </CardContent>
        </Card>
        <div className="space-y-4">
          {active ? (
            <Card>
              <CardHeader>
                <CardTitle>人物详情：{active.name}</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 md:grid-cols-2">
                <BibleBlock title="动机" text={active.motivation || "—"} />
                <BibleBlock title="秘密" text={active.secret || "—"} />
                <BibleBlock title="角色定位" text={active.role || "—"} />
                <BibleBlock title="描述" text={active.description || "—"} />
              </CardContent>
            </Card>
          ) : null}
          <Card>
            <CardHeader>
              <CardTitle>人物关系图</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-3">
                {characters.map((character) => (
                  <div
                    key={character.id}
                    className="rounded-2xl border border-slate-200 bg-white p-4 text-center"
                  >
                    <div className="mx-auto grid size-12 place-items-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 text-lg font-black text-white">
                      {character.name.slice(0, 1)}
                    </div>
                    <p className="mt-2 font-bold text-slate-950">{character.name}</p>
                    <p className="text-xs text-slate-500">{character.role}</p>
                  </div>
                ))}
              </div>
              <div className="mt-4 rounded-2xl bg-slate-50 p-4 text-sm text-slate-600">
                <Network className="mr-2 inline size-4 text-indigo-600" />
                关系边由 Memory Engine 自动写入。
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

// =========== 世界观 ===========
export function WorldPage({ projectId }: { projectId: string }) {
  const { data: items = [] } = useQuery({
    queryKey: useScopedKey("project", projectId, "world-items"),
    queryFn: () => worldItemsApi.list(projectId) as Promise<WorldItem[]>,
  });
  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      {items.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">
            尚无世界观条目，可在生成大纲时自动产出，或手动添加。
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {items.map((item) => (
            <Card key={item.id}>
              <CardContent>
                <Badge tone="blue">{item.type}</Badge>
                <h3 className="mt-3 text-lg font-black text-slate-950">{item.name}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-500">
                  {item.description.slice(0, 120)}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Lorebook 检索</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
          <ActionCard title="地点" description="按 type=location 过滤" href="#" icon={Boxes} tone="violet" />
          <ActionCard title="组织" description="按 type=organization 过滤" href="#" icon={Users} tone="blue" />
          <ActionCard title="规则" description="按 type=rule 过滤" href="#" icon={BookOpen} tone="green" />
        </CardContent>
      </Card>
    </div>
  );
}

// =========== 大纲 ===========
export function OutlinePage({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const projectKey = useScopedKey("project", projectId);
  const chaptersKey = useScopedKey("project", projectId, "chapters");
  const jobsKey = useScopedKey("jobs");

  const { data: chapters = [] } = useQuery({
    queryKey: chaptersKey,
    queryFn: () => chaptersApi.list(projectId),
  });

  // 找出本项目的 generate_outline 任务最近一条（jobs.list 默认 created_at desc）。
  // 用于驱动生成按钮的 loading 态与轮询刷新。
  const { data: jobs = [] } = useQuery({
    queryKey: jobsKey,
    queryFn: () => jobsApi.list() as Promise<GenerationJob[]>,
    refetchInterval: (query) => {
      const list = (query.state.data as GenerationJob[] | undefined) ?? [];
      const projectActive = list.find(
        (j) =>
          j.project_id === projectId &&
          (j.job_type === "generate_outline" || j.job_type === "generate_scene_plan") &&
          (j.status === "queued" || j.status === "running"),
      );
      const waitingForChapters =
        list.some(
          (j) =>
            j.project_id === projectId &&
            j.job_type === "generate_outline" &&
            j.status === "succeeded",
        ) && chapters.length === 0;
      return projectActive || waitingForChapters ? 1500 : false;
    },
  });
  const latestJob = jobs.find(
    (j) => j.project_id === projectId && j.job_type === "generate_outline",
  );
  const isGenerating = latestJob?.status === "queued" || latestJob?.status === "running";

  const generate = useMutation({
    mutationFn: () =>
      projectsApi.generateOutline(projectId, {
        estimate_words: 3000,
        force_regenerate: chapters.length > 0,
      }),
    onSuccess: () => {
      toast.success("已提交章节大纲生成任务");
      queryClient.invalidateQueries({ queryKey: chaptersKey });
      queryClient.invalidateQueries({ queryKey: projectKey });
      queryClient.invalidateQueries({ queryKey: jobsKey });
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "提交失败");
    },
  });

  const [activeId, setActiveId] = useState<string | null>(null);
  const active = chapters.find((c) => c.id === activeId) ?? chapters[0];

  // 当前激活章节的 scene_plan 任务（按 input_payload.chapter_id 精确匹配）
  const latestSceneJob = jobs.find(
    (j) =>
      j.project_id === projectId &&
      j.job_type === "generate_scene_plan" &&
      (j.input_payload as { chapter_id?: string } | null | undefined)?.chapter_id ===
        active?.id,
  );
  const isGeneratingScenes =
    latestSceneJob?.status === "queued" || latestSceneJob?.status === "running";

  const scenesKey = useScopedKey("project", projectId, "scenes", active?.id);
  const { data: scenes = [] } = useQuery({
    queryKey: scenesKey,
    queryFn: () => scenesApi.list(projectId, active?.id),
    enabled: !!active,
  });

  const generateScenes = useMutation({
    mutationFn: () => {
      if (!active) {
        return Promise.reject(new Error("no_active_chapter"));
      }
      return projectsApi.generateScenePlan(projectId, active.id, {
        scenes_per_chapter: 3,
        expected_words: 1500,
        estimate_words: 2000,
        force_regenerate: scenes.length > 0,
      });
    },
    onSuccess: () => {
      toast.success("已提交场景计划生成任务");
      queryClient.invalidateQueries({ queryKey: scenesKey });
      queryClient.invalidateQueries({ queryKey: jobsKey });
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "提交失败");
    },
  });

  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>章节大纲 Outline</CardTitle>
            <p className="mt-1 text-sm text-slate-500">
              依赖故事圣经；生成后会同步写入 chapters 表并更新项目状态。
            </p>
          </div>
          <div className="flex items-center gap-2">
            {latestJob ? <StatusBadge status={latestJob.status as never} /> : null}
            <Badge tone={chapters.length > 0 ? "blue" : "slate"}>
              {chapters.length > 0 ? `已生成 ${chapters.length} 章` : "未生成"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-slate-50 p-4">
            <div>
              <p className="font-bold text-slate-950">Sprint 2 大纲闭环</p>
              <p className="text-sm text-slate-500">
                调用模型规划三幕推进，每章产出标题、摘要、目标、冲突、结尾钩子。
              </p>
            </div>
            <Button
              onClick={() => generate.mutate()}
              disabled={generate.isPending || isGenerating}
            >
              {isGenerating ? (
                <RefreshCw className="size-4 animate-spin" />
              ) : (
                <Sparkles className="size-4" />
              )}
              {chapters.length > 0 ? "重新生成大纲" : "启动生成"}
            </Button>
          </div>
          {latestJob ? (
            <div className="grid gap-3 md:grid-cols-3">
              <BibleBlock title="任务类型" text={latestJob.job_type} />
              <BibleBlock
                title="额度"
                text={`${latestJob.consumed_quota}/${latestJob.reserved_quota}`}
              />
              <BibleBlock title="Workflow" text={latestJob.workflow_id ?? "—"} />
            </div>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[0.75fr_1.25fr]">
        <Card>
          <CardHeader>
            <CardTitle>章节大纲树</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {chapters.length === 0 ? (
              <p className="py-8 text-center text-sm text-slate-500">尚未生成章节大纲。</p>
            ) : (
              chapters.map((chapter) => (
                <button
                  key={chapter.id}
                  type="button"
                  onClick={() => setActiveId(chapter.id)}
                  className={`w-full rounded-2xl border p-4 text-left ${
                    active?.id === chapter.id ? "border-indigo-300 bg-indigo-50" : "border-slate-200"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <p className="font-bold text-slate-950">
                      第 {chapter.chapter_index} 章 · {chapter.title}
                    </p>
                    <StatusBadge status={chapter.status as never} />
                  </div>
                  <p className="mt-1 text-sm text-slate-500">{chapter.summary}</p>
                </button>
              ))
            )}
          </CardContent>
        </Card>
        {active ? (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>当前章节大纲</CardTitle>
              <Badge tone="violet">可生成场景拆分</Badge>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <BibleBlock title="章节目标" text={active.goal || "—"} />
                <BibleBlock title="核心冲突" text={active.conflict || "—"} />
                <BibleBlock title="结尾钩子" text={active.ending_hook || "—"} />
                <BibleBlock title="摘要" text={active.summary || "—"} />
              </div>
              <DataTable
                rows={scenes}
                columns={[
                  {
                    key: "scene",
                    header: "场景",
                    render: (row) => (
                      <span className="font-bold text-slate-950">
                        场景 {row.scene_index} · {row.title}
                      </span>
                    ),
                  },
                  { key: "location", header: "地点", render: (row) => row.location || "—" },
                  { key: "goal", header: "目标", render: (row) => row.goal || "—" },
                  {
                    key: "status",
                    header: "状态",
                    render: (row) => <StatusBadge status={row.status as never} />,
                  },
                ]}
              />
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-slate-50 p-4">
                <div>
                  <p className="font-bold text-slate-950">下一步</p>
                  <p className="text-sm text-slate-500">
                    场景生成会创建 generation_job 并预留额度（Sprint 3 闭环）。
                  </p>
                  {latestSceneJob ? (
                    <p className="mt-1 text-xs text-slate-500">
                      最近任务：{latestSceneJob.status} · 额度{" "}
                      {latestSceneJob.consumed_quota}/{latestSceneJob.reserved_quota}
                    </p>
                  ) : null}
                </div>
                <Button
                  onClick={() => generateScenes.mutate()}
                  disabled={generateScenes.isPending || isGeneratingScenes || !active}
                >
                  {isGeneratingScenes ? (
                    <RefreshCw className="size-4 animate-spin" />
                  ) : (
                    <Wand2 className="size-4" />
                  )}
                  {scenes.length > 0 ? "重新生成场景计划" : "生成场景计划"}
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : null}
      </div>
    </div>
  );
}

// =========== 写作工作台 ===========

/**
 * ContextBuilder Inspector 显示的单段摘要结构。
 * 与 backend/app/workflows/activities.py::run_scene_writing 返回的
 * output_payload.context_summary 对齐。
 */
type ContextSummaryEntry = {
  label: string;
  trusted: boolean;
  token_budget: number;
  estimated_tokens: number;
  truncated: boolean;
  preview: string;
};

function ContextInspector({
  summary,
}: {
  summary?: {
    context_summary?: ContextSummaryEntry[];
    context_total_tokens?: number;
  } | null;
}) {
  const segments = summary?.context_summary ?? [];
  if (segments.length === 0) return null;
  return (
    <div className="space-y-2 border-t border-slate-100 pt-3 text-xs text-slate-500">
      <div className="flex items-center justify-between">
        <p className="font-bold text-slate-950">ContextBuilder Inspector</p>
        <span className="text-xs">
          总 tokens：{summary?.context_total_tokens ?? 0}
        </span>
      </div>
      {segments.map((seg) => (
        <details key={seg.label} className="rounded-md border border-slate-100">
          <summary className="cursor-pointer px-2 py-1">
            <span className="font-mono text-slate-700">{seg.label}</span>
            <span className="ml-2 text-slate-400">
              {seg.estimated_tokens}/{seg.token_budget}t
            </span>
            {!seg.trusted ? (
              <Badge tone="amber" className="ml-2">
                untrusted
              </Badge>
            ) : null}
            {seg.truncated ? (
              <Badge tone="rose" className="ml-2">
                truncated
              </Badge>
            ) : null}
          </summary>
          <pre className="m-0 whitespace-pre-wrap px-2 pb-2 text-xs text-slate-500">
            {seg.preview}
            {seg.truncated ? "…" : ""}
          </pre>
        </details>
      ))}
    </div>
  );
}

function labelForVersion(versions: DraftVersion[], versionId: string): string {
  const idx = versions.findIndex((v) => v.id === versionId);
  if (idx < 0) return "未知版本";
  return `第 ${versions.length - idx} 版`;
}

function severityTone(severity: string): "rose" | "amber" | "slate" {
  switch (severity) {
    case "high":
      return "rose";
    case "medium":
      return "amber";
    default:
      return "slate";
  }
}

function severityClass(severity: string): string {
  switch (severity) {
    case "high":
      return "border-rose-200 bg-rose-50/40";
    case "medium":
      return "border-amber-200 bg-amber-50/40";
    default:
      return "border-slate-200";
  }
}

/**
 * Editor + dirty 检测 + 保存按钮 + 自动保存（debounce 15s）的子组件。
 *
 * 父组件用 `key={version.id}` 控制 remount，避免在 useEffect 中直接 setState
 * 同步 props → state（React 19 的 set-state-in-effect 反模式）。
 */
function SceneEditorCard({
  version,
  editable,
  isSaving,
  onSave,
  onAutoSave,
}: {
  version: DraftVersion;
  editable: boolean;
  isSaving: boolean;
  onSave: (content: string) => void;
  onAutoSave?: (content: string) => void;
}) {
  const [content, setContent] = useState(version.content);
  const isDirty = content !== version.content;

  // 用 ref 持有最新 onAutoSave 引用，避免 useCallback 链反复重置 debounce timer。
  // ref 赋值在 useEffect 内完成以符合 React 19 的 refs-in-render 规则。
  const autoSaveRef = useRef(onAutoSave);
  useEffect(() => {
    autoSaveRef.current = onAutoSave;
  }, [onAutoSave]);

  // 自动保存：editable 且 dirty 时启动 15s debounce；任意编辑动作都会重置 timer。
  useEffect(() => {
    if (!editable || !isDirty) return;
    const timer = setTimeout(() => {
      autoSaveRef.current?.(content);
    }, 15_000);
    return () => clearTimeout(timer);
  }, [content, editable, isDirty]);

  return (
    <>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          {isDirty ? <Badge tone="violet">未保存</Badge> : null}
          {!editable ? <Badge tone="amber">预览历史版本</Badge> : null}
          {editable && isDirty && onAutoSave ? (
            <span className="text-xs text-slate-400">15s 后自动保存</span>
          ) : null}
        </div>
        {editable ? (
          <Button
            variant="secondary"
            onClick={() => onSave(content)}
            disabled={!isDirty || isSaving}
          >
            <FileArchive className="size-4" />
            保存版本
          </Button>
        ) : null}
      </div>
      <SceneEditor content={content} onChange={setContent} editable={editable} />
    </>
  );
}

export function WritingWorkspacePage({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const chaptersKey = useScopedKey("project", projectId, "chapters");
  const jobsKey = useScopedKey("jobs");
  const preflightKey = useScopedKey("project", projectId, "preflight", "write_scene");

  const { data: chapters = [] } = useQuery({
    queryKey: chaptersKey,
    queryFn: () => chaptersApi.list(projectId),
  });
  const { data: preflight } = useQuery({
    queryKey: preflightKey,
    queryFn: () => projectsApi.preflight(projectId, "write_scene"),
  });

  const [activeChapterId, setActiveChapterId] = useState<string | null>(null);
  const activeChapter =
    chapters.find((c) => c.id === activeChapterId) ?? chapters[0];

  const scenesKey = useScopedKey(
    "project",
    projectId,
    "scenes",
    activeChapter?.id,
  );
  const { data: scenes = [] } = useQuery({
    queryKey: scenesKey,
    queryFn: () => scenesApi.list(projectId, activeChapter?.id),
    enabled: !!activeChapter,
  });

  const [activeSceneId, setActiveSceneId] = useState<string | null>(null);
  const activeScene = scenes.find((s) => s.id === activeSceneId) ?? scenes[0];

  // 当前 scene 的 draft_versions（base list 默认按 created_at desc）
  const versionsKey = useScopedKey(
    "project",
    projectId,
    "versions",
    activeScene?.id,
  );
  const { data: versions = [] } = useQuery({
    queryKey: versionsKey,
    queryFn: () => versionsApi.list(projectId, { scene_id: activeScene?.id }),
    enabled: !!activeScene,
  });
  const latestDraft: DraftVersion | undefined = versions[0];

  // 显示的版本：默认最新；如果切换到了某历史版本，记录其 id。当 scene 改变
  // 或 versions 列表变化导致该 id 失效时，displayedVersion 自动 fallback
  // 到 latestDraft，无需用 useEffect 重置 displayedVersionId。
  const [displayedVersionId, setDisplayedVersionId] = useState<string | null>(null);
  const displayedVersion =
    (displayedVersionId
      ? versions.find((v) => v.id === displayedVersionId)
      : undefined) ?? latestDraft;
  const isShowingLatest =
    !displayedVersion || displayedVersion.id === latestDraft?.id;

  // 对比模式：与当前 displayedVersion 对比的另一个版本 id。null = 普通编辑模式。
  const [compareWithId, setCompareWithId] = useState<string | null>(null);
  const compareWithVersion = compareWithId
    ? versions.find((v) => v.id === compareWithId)
    : undefined;
  const isComparing = !!compareWithVersion;

  // 当前 scene 的 write_scene 任务（按 input_payload.scene_id 过滤）
  const { data: jobs = [] } = useQuery({
    queryKey: jobsKey,
    queryFn: () => jobsApi.list() as Promise<GenerationJob[]>,
    refetchInterval: (query) => {
      const list = (query.state.data as GenerationJob[] | undefined) ?? [];
      const active = list.find(
        (j) =>
          j.project_id === projectId &&
          ["write_scene", "audit_scene", "rewrite_scene"].includes(j.job_type) &&
          (j.status === "queued" || j.status === "running"),
      );
      return active ? 1500 : false;
    },
  });
  const latestSceneJob = jobs.find(
    (j) =>
      j.project_id === projectId &&
      j.job_type === "write_scene" &&
      (j.input_payload as { scene_id?: string } | null | undefined)?.scene_id ===
        activeScene?.id,
  );
  const isWriting =
    latestSceneJob?.status === "queued" || latestSceneJob?.status === "running";

  const write = useMutation({
    mutationFn: () => {
      if (!activeScene) {
        return Promise.reject(new Error("no_active_scene"));
      }
      return projectsApi.writeScene(projectId, activeScene.id, {
        target_words: 1200,
      });
    },
    onSuccess: () => {
      toast.success("已提交场景写作任务");
      queryClient.invalidateQueries({ queryKey: jobsKey });
      queryClient.invalidateQueries({ queryKey: scenesKey });
      queryClient.invalidateQueries({ queryKey: versionsKey });
      queryClient.invalidateQueries({ queryKey: preflightKey });
      setDisplayedVersionId(null);
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "提交失败");
    },
  });

  const saveVersion = useMutation({
    mutationFn: (content: string) => {
      if (!activeScene || !activeChapter) {
        return Promise.reject(new Error("no_active_scene"));
      }
      return versionsApi.create(projectId, {
        chapter_id: activeChapter.id,
        scene_id: activeScene.id,
        version_type: "user",
        content,
        word_count: content.length,
        status: "draft",
        parent_version_id: displayedVersion?.id ?? null,
      });
    },
    onSuccess: () => {
      toast.success("已保存为新版本");
      queryClient.invalidateQueries({ queryKey: versionsKey });
      setDisplayedVersionId(null);
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "保存失败");
    },
  });

  const autoSave = useMutation({
    // autosave 默默成功；与手动保存的差别：不弹 toast、version_type=autosave。
    mutationFn: (content: string) => {
      if (!activeScene || !activeChapter) {
        return Promise.reject(new Error("no_active_scene"));
      }
      return versionsApi.create(projectId, {
        chapter_id: activeChapter.id,
        scene_id: activeScene.id,
        version_type: "autosave",
        content,
        word_count: content.length,
        status: "draft",
        parent_version_id: displayedVersion?.id ?? null,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: versionsKey });
      setDisplayedVersionId(null);
    },
    onError: (e: unknown) => {
      // autosave 失败不打断用户，仅 console.warn
      console.warn("autosave failed", e);
    },
  });

  const deleteVersion = useMutation({
    mutationFn: (versionId: string) => versionsApi.delete(projectId, versionId),
    onSuccess: (_, versionId) => {
      toast.success("已删除该版本");
      // 若当前预览的就是被删的版本，自动回到最新版
      if (displayedVersionId === versionId) {
        setDisplayedVersionId(null);
      }
      queryClient.invalidateQueries({ queryKey: versionsKey });
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "删除失败");
    },
  });

  // 审稿 / 重写：本 scene 的 ContinuityIssue 列表
  const issuesKey = useScopedKey("project", projectId, "continuity-issues");
  const { data: allIssues = [] } = useQuery({
    queryKey: issuesKey,
    queryFn: () => continuityIssuesApi.list(projectId),
    enabled: !!activeScene,
  });
  const sceneIssues = allIssues.filter((i) => i.scene_id === activeScene?.id);
  const sceneOpenIssues = sceneIssues.filter((i) => i.status === "open");

  const audit = useMutation({
    mutationFn: () => {
      if (!activeScene) {
        return Promise.reject(new Error("no_active_scene"));
      }
      return projectsApi.auditScene(projectId, activeScene.id, {
        estimate_words: 500,
      });
    },
    onSuccess: () => {
      toast.success("已提交审稿任务");
      queryClient.invalidateQueries({ queryKey: jobsKey });
      queryClient.invalidateQueries({ queryKey: issuesKey });
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "审稿提交失败");
    },
  });

  const rewrite = useMutation({
    mutationFn: () => {
      if (!activeScene) {
        return Promise.reject(new Error("no_active_scene"));
      }
      return projectsApi.rewriteScene(projectId, activeScene.id, {
        target_words: 1200,
        estimate_words: 2000,
      });
    },
    onSuccess: () => {
      toast.success("已提交重写任务");
      queryClient.invalidateQueries({ queryKey: jobsKey });
      queryClient.invalidateQueries({ queryKey: issuesKey });
      queryClient.invalidateQueries({ queryKey: scenesKey });
      queryClient.invalidateQueries({ queryKey: versionsKey });
      setDisplayedVersionId(null);
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "重写提交失败");
    },
  });

  // audit/rewrite 任务"正在进行"判断（基于 job.input_payload.scene_id）
  const latestAuditJob = jobs.find(
    (j) =>
      j.project_id === projectId &&
      j.job_type === "audit_scene" &&
      (j.input_payload as { scene_id?: string } | null | undefined)?.scene_id ===
        activeScene?.id,
  );
  const isAuditing =
    latestAuditJob?.status === "queued" || latestAuditJob?.status === "running";
  const latestRewriteJob = jobs.find(
    (j) =>
      j.project_id === projectId &&
      j.job_type === "rewrite_scene" &&
      (j.input_payload as { scene_id?: string } | null | undefined)?.scene_id ===
        activeScene?.id,
  );
  const isRewriting =
    latestRewriteJob?.status === "queued" || latestRewriteJob?.status === "running";

  return (
    <div className="space-y-4">
      <ProjectHeader projectId={projectId} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-black text-slate-950">写作工作台</h1>
          <p className="mt-1 text-sm text-slate-500">
            Sprint 4：ContextBuilder + draft 版本链 + Tiptap 编辑器。
          </p>
        </div>
        <Button
          onClick={() => write.mutate()}
          disabled={
            write.isPending ||
            isWriting ||
            !activeScene ||
            (preflight?.can_generate === false)
          }
        >
          {isWriting ? (
            <RefreshCw className="size-4 animate-spin" />
          ) : (
            <Sparkles className="size-4" />
          )}
          {latestDraft ? "重新生成场景" : "生成当前场景"}
        </Button>
      </div>
      {preflight && preflight.can_generate === false ? (
        <PreflightCard report={preflight} />
      ) : null}
      <div className="grid min-h-[420px] gap-4 xl:grid-cols-[280px_minmax(520px,1fr)_340px]">
        <Card>
          <CardHeader>
            <CardTitle>章节 / 场景</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {chapters.length === 0 ? (
              <p className="text-sm text-slate-500">尚未生成章节大纲。</p>
            ) : (
              chapters.map((chapter) => (
                <div key={chapter.id} className="space-y-1">
                  <button
                    type="button"
                    onClick={() => {
                      setActiveChapterId(chapter.id);
                      setActiveSceneId(null);
                      setDisplayedVersionId(null);
                      setCompareWithId(null);
                    }}
                    className={`w-full rounded-xl border p-3 text-left text-sm ${
                      activeChapter?.id === chapter.id
                        ? "border-indigo-300 bg-indigo-50"
                        : "border-slate-200"
                    }`}
                  >
                    <p className="font-bold text-slate-950">
                      第 {chapter.chapter_index} 章 · {chapter.title}
                    </p>
                  </button>
                  {activeChapter?.id === chapter.id && scenes.length > 0 ? (
                    <div className="space-y-1 pl-3">
                      {scenes.map((scene) => (
                        <button
                          key={scene.id}
                          type="button"
                          onClick={() => {
                            setActiveSceneId(scene.id);
                            setDisplayedVersionId(null);
                            setCompareWithId(null);
                          }}
                          className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left text-xs ${
                            activeScene?.id === scene.id
                              ? "border-indigo-300 bg-indigo-50"
                              : "border-slate-100"
                          }`}
                        >
                          <span className="truncate">
                            场景 {scene.scene_index} · {scene.title}
                          </span>
                          <StatusBadge status={scene.status as never} />
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>{activeScene ? activeScene.title : "未选择场景"}</CardTitle>
              {activeScene ? (
                <p className="mt-1 text-xs text-slate-500">
                  {activeScene.location} · {activeScene.time_marker} ·{" "}
                  {activeScene.characters?.join(", ") || "—"}
                </p>
              ) : null}
            </div>
            <div className="flex items-center gap-2">
              {latestSceneJob ? (
                <StatusBadge status={latestSceneJob.status as never} />
              ) : null}
              {activeScene ? (
                <Badge tone={latestDraft ? "blue" : "slate"}>
                  {latestDraft
                    ? `第 ${versions.length} 版 · ${displayedVersion?.word_count ?? 0} 字`
                    : "未生成"}
                </Badge>
              ) : null}
            </div>
          </CardHeader>
          <CardContent>
            {!activeScene ? (
              <p className="py-12 text-center text-sm text-slate-500">
                从左侧选择一个场景开始写作。
              </p>
            ) : !displayedVersion ? (
              <div className="space-y-3">
                <p className="text-sm text-slate-500">
                  此场景还没有 draft。点击右上「生成当前场景」，ContextBuilder
                  会装配 7 段优先级上下文交给模型。
                </p>
                <div className="grid gap-3 md:grid-cols-2">
                  <BibleBlock title="场景目标" text={activeScene.goal || "—"} />
                  <BibleBlock title="微冲突" text={activeScene.conflict || "—"} />
                  <BibleBlock
                    title="情绪变化"
                    text={`${activeScene.emotion_start} → ${activeScene.emotion_end}`}
                  />
                  <BibleBlock title="钩子" text={activeScene.hook || "—"} />
                </div>
              </div>
            ) : isComparing && compareWithVersion ? (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-xs text-slate-500">
                    对比：
                    <span className="font-bold text-slate-700">
                      {labelForVersion(versions, compareWithVersion.id)}
                    </span>
                    {" → "}
                    <span className="font-bold text-slate-950">
                      {labelForVersion(versions, displayedVersion.id)}
                    </span>
                  </div>
                  <Button
                    variant="ghost"
                    onClick={() => setCompareWithId(null)}
                  >
                    退出对比
                  </Button>
                </div>
                <DiffView
                  oldContent={compareWithVersion.content}
                  newContent={displayedVersion.content}
                  oldLabel={labelForVersion(versions, compareWithVersion.id)}
                  newLabel={labelForVersion(versions, displayedVersion.id)}
                />
              </div>
            ) : (
              <SceneEditorCard
                key={displayedVersion.id}
                version={displayedVersion}
                editable={isShowingLatest}
                isSaving={saveVersion.isPending}
                onSave={(content) => saveVersion.mutate(content)}
                onAutoSave={(content) => autoSave.mutate(content)}
              />
            )}
            {/* Sprint 5-A：审稿与重写面板。仅当 scene 已有 draft 且非对比模式时显示 */}
            {activeScene && displayedVersion && !isComparing ? (
              <div className="mt-4 space-y-3 border-t border-slate-100 pt-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="font-bold text-slate-950">审稿 & 问题</p>
                    <p className="text-xs text-slate-500">
                      {sceneOpenIssues.length > 0
                        ? `当前发现 ${sceneOpenIssues.length} 个待修复问题`
                        : "当前未发现连续性问题"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="secondary"
                      onClick={() => audit.mutate()}
                      disabled={audit.isPending || isAuditing || !isShowingLatest}
                      title={
                        !isShowingLatest
                          ? "请先切回最新版本再审稿"
                          : "对最新 draft 触发连续性审稿"
                      }
                    >
                      {isAuditing ? (
                        <RefreshCw className="size-4 animate-spin" />
                      ) : (
                        <CheckCircle2 className="size-4" />
                      )}
                      审稿
                    </Button>
                    <Button
                      onClick={() => rewrite.mutate()}
                      disabled={
                        rewrite.isPending ||
                        isRewriting ||
                        !isShowingLatest ||
                        sceneOpenIssues.length === 0
                      }
                      title={
                        sceneOpenIssues.length === 0
                          ? "无待修复问题"
                          : "基于当前问题列表重写正文"
                      }
                    >
                      {isRewriting ? (
                        <RefreshCw className="size-4 animate-spin" />
                      ) : (
                        <Wand2 className="size-4" />
                      )}
                      重写并修复
                    </Button>
                  </div>
                </div>
                {sceneIssues.length === 0 ? (
                  <p className="text-sm text-slate-500">
                    点击「审稿」让 ContextBuilder 把当前 draft + 全局上下文
                    送给模型，发现的问题会落到 continuity_issues 表。
                  </p>
                ) : (
                  <ul className="space-y-2">
                    {sceneIssues.map((issue) => (
                      <li
                        key={issue.id}
                        className={`rounded-xl border p-3 text-xs ${
                          issue.status === "fixed"
                            ? "border-emerald-200 bg-emerald-50/40"
                            : severityClass(issue.severity)
                        }`}
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge tone={severityTone(issue.severity)}>
                            {issue.severity}
                          </Badge>
                          <Badge tone="slate">{issue.issue_type}</Badge>
                          <Badge tone={issue.status === "fixed" ? "green" : "amber"}>
                            {issue.status}
                          </Badge>
                        </div>
                        <p className="mt-2 font-semibold text-slate-950">
                          {issue.description}
                        </p>
                        {issue.suggested_fix ? (
                          <p className="mt-1 text-slate-600">
                            建议：{issue.suggested_fix}
                          </p>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>版本历史</CardTitle>
            <Badge tone="slate">{versions.length}</Badge>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {versions.length === 0 ? (
              <p className="text-xs text-slate-500">尚无版本。</p>
            ) : (
              <>
                {versions.map((v, idx) => {
                  const isActive = displayedVersion?.id === v.id;
                  const isLatest = v.id === latestDraft?.id;
                  return (
                    <div
                      key={v.id}
                      className={`group relative rounded-xl border ${
                        isActive
                          ? "border-indigo-300 bg-indigo-50"
                          : "border-slate-200 hover:bg-slate-50"
                      }`}
                    >
                      <button
                        type="button"
                        onClick={() =>
                          setDisplayedVersionId(isLatest ? null : v.id)
                        }
                        className="w-full p-3 text-left text-xs"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-bold text-slate-950">
                            第 {versions.length - idx} 版
                          </span>
                          <Badge tone={v.version_type === "user" ? "violet" : "blue"}>
                            {v.version_type}
                          </Badge>
                        </div>
                        <p className="mt-1 text-slate-500">
                          {v.word_count} 字 · {v.status}
                        </p>
                      </button>
                      <div className="absolute right-2 top-2 flex gap-1">
                        {!isActive ? (
                          <button
                            type="button"
                            aria-label="与当前版本对比"
                            onClick={() => setCompareWithId(v.id)}
                            disabled={!displayedVersion}
                            className="rounded-md p-1 text-slate-400 opacity-0 transition group-hover:opacity-100 hover:bg-indigo-50 hover:text-indigo-600"
                          >
                            <GitCompare className="size-3.5" />
                          </button>
                        ) : null}
                        <button
                          type="button"
                          aria-label="删除版本"
                          onClick={() => {
                            // 简单二次确认；如果业务要更严肃可改 dialog
                            if (
                              window.confirm(
                                `确定删除第 ${versions.length - idx} 版？此操作不可恢复。`,
                              )
                            ) {
                              deleteVersion.mutate(v.id);
                            }
                          }}
                          disabled={deleteVersion.isPending}
                          className="rounded-md p-1 text-slate-400 opacity-0 transition group-hover:opacity-100 hover:bg-rose-50 hover:text-rose-600 disabled:opacity-30"
                        >
                          <Trash2 className="size-3.5" />
                        </button>
                      </div>
                    </div>
                  );
                })}
                {!isShowingLatest ? (
                  <Button
                    variant="ghost"
                    onClick={() => setDisplayedVersionId(null)}
                    className="w-full"
                  >
                    返回最新版本
                  </Button>
                ) : null}
              </>
            )}
            {latestSceneJob ? (
              <div className="pt-2 text-xs text-slate-500">
                <p className="font-bold text-slate-950">最近任务</p>
                <p>
                  额度：{latestSceneJob.consumed_quota}/{latestSceneJob.reserved_quota}
                </p>
                <p>Workflow：{latestSceneJob.workflow_id ?? "—"}</p>
              </div>
            ) : null}
            <ContextInspector
              summary={
                (latestSceneJob?.output_payload as
                  | { context_summary?: ContextSummaryEntry[]; context_total_tokens?: number }
                  | null
                  | undefined)
              }
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function StatJob({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: number;
  icon: typeof TimerReset;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4">
        <div className="grid size-12 place-items-center rounded-2xl bg-indigo-50 text-indigo-600">
          <Icon className="size-6" />
        </div>
        <div>
          <p className="text-sm text-slate-500">{label}</p>
          <p className="text-3xl font-black text-slate-950">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}

// =========== 任务 ===========
export function JobsPage({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const { data: allJobs = [] } = useQuery({
    queryKey: useScopedKey("jobs"),
    queryFn: () => jobsApi.list() as Promise<Job[]>,
  });
  const rows = allJobs.filter((j) => j.project_id === projectId);

  const cancel = useMutation({
    mutationFn: (id: string) => jobsApi.cancel(id),
    onSuccess: () => {
      toast.success("已取消");
      queryClient.invalidateQueries({ queryKey: ["org"] });
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "取消失败"),
  });

  const retry = useMutation({
    mutationFn: (id: string) => jobsApi.retry(id),
    onSuccess: (newJob) => {
      toast.success(`已重新提交任务（${newJob.job_type}）`);
      queryClient.invalidateQueries({ queryKey: ["org"] });
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "重试失败"),
  });

  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <div className="grid gap-4 lg:grid-cols-4">
        <StatJob
          label="队列中"
          value={rows.filter((j) => j.status === "queued").length}
          icon={TimerReset}
        />
        <StatJob
          label="运行中"
          value={rows.filter((j) => j.status === "running").length}
          icon={RefreshCw}
        />
        <StatJob
          label="已失败"
          value={rows.filter((j) => j.status === "failed").length}
          icon={XCircle}
        />
        <StatJob
          label="已完成"
          value={rows.filter((j) => j.status === "succeeded").length}
          icon={CheckCircle2}
        />
      </div>
      <Card>
        <CardHeader>
          <CardTitle>任务队列</CardTitle>
        </CardHeader>
        <CardContent>
          {rows.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">该项目暂无生成任务。</p>
          ) : (
            <DataTable
              rows={rows}
              columns={[
                {
                  key: "title",
                  header: "任务",
                  render: (row) => (
                    <div>
                      <p className="font-bold text-slate-950">{row.job_type}</p>
                      <p className="text-xs text-slate-500">{row.workflow_id ?? "—"}</p>
                    </div>
                  ),
                },
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
                    <ProgressBar
                      value={(row.consumed_quota / Math.max(row.reserved_quota, 1)) * 100}
                    />
                  ),
                },
                {
                  key: "actions",
                  header: "操作",
                  render: (row) => {
                    if (row.status === "queued" || row.status === "running") {
                      return (
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() => cancel.mutate(row.id)}
                          disabled={cancel.isPending}
                        >
                          取消
                        </Button>
                      );
                    }
                    if (row.status === "failed" || row.status === "cancelled") {
                      return (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => retry.mutate(row.id)}
                          disabled={retry.isPending}
                        >
                          <RefreshCw className="size-4" /> 重试
                        </Button>
                      );
                    }
                    return null;
                  },
                },
              ]}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// =========== 版本 ===========
export function VersionsPage({ projectId }: { projectId: string }) {
  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <Card>
        <CardHeader>
          <CardTitle>版本历史</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-500">
            版本接口 GET /projects/:id/versions 已就绪，UI 展示组件待落地。
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

// =========== 导出 ===========
export function ExportPage({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const exportsKey = useScopedKey("project", projectId, "exports");
  const { data: files = [] } = useQuery({
    queryKey: exportsKey,
    queryFn: () => exportsApi.list(projectId),
  });
  const create = useMutation({
    mutationFn: (export_type: string) => exportsApi.create(projectId, export_type),
    onSuccess: (created) => {
      toast.success(
        `已生成 ${created.export_type.toUpperCase()}（${formatBytes(created.file_size)}）`,
      );
      queryClient.invalidateQueries({ queryKey: exportsKey });
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "创建失败"),
  });
  const download = useMutation({
    mutationFn: (exportId: string) => exportsApi.download(projectId, exportId),
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "下载失败"),
  });

  // Sprint 5-B 仅支持 markdown / txt；docx/epub/pdf 由 Sprint 6 接入 MinIO + 真实渲染时启用
  const formats: { value: string; label: string; supported: boolean }[] = [
    { value: "markdown", label: "Markdown", supported: true },
    { value: "txt", label: "TXT", supported: true },
    { value: "docx", label: "DOCX", supported: false },
    { value: "epub", label: "EPUB", supported: false },
    { value: "pdf", label: "PDF", supported: false },
  ];

  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <div className="grid gap-4 md:grid-cols-5">
        {formats.map((format) => (
          <Card key={format.value}>
            <CardContent className="text-center">
              <FileArchive
                className={`mx-auto size-9 ${
                  format.supported ? "text-indigo-600" : "text-slate-300"
                }`}
              />
              <h3 className="mt-3 font-black uppercase text-slate-950">
                {format.label}
              </h3>
              {!format.supported ? (
                <p className="mt-1 text-xs text-slate-400">Sprint 6 接入</p>
              ) : null}
              <Button
                className="mt-4 w-full"
                size="sm"
                onClick={() => create.mutate(format.value)}
                disabled={create.isPending || !format.supported}
              >
                {create.isPending ? "生成中..." : "开始导出"}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>最近导出文件</CardTitle>
        </CardHeader>
        <CardContent>
          {files.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">暂无导出记录。</p>
          ) : (
            <DataTable
              rows={files}
              columns={[
                {
                  key: "format",
                  header: "格式",
                  render: (row) => row.export_type.toUpperCase(),
                },
                {
                  key: "status",
                  header: "状态",
                  render: (row) => (
                    <StatusBadge
                      status={row.status === "ready" ? "succeeded" : (row.status as never)}
                    />
                  ),
                },
                {
                  key: "size",
                  header: "大小",
                  render: (row) => formatBytes(row.file_size),
                },
                {
                  key: "time",
                  header: "时间",
                  render: (row) => (row.created_at ? formatDateTime(row.created_at) : "—"),
                },
                {
                  key: "download",
                  header: "操作",
                  render: (row) =>
                    row.status === "ready" ? (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => download.mutate(row.id)}
                        disabled={download.isPending}
                      >
                        <Download className="size-4" /> 下载
                      </Button>
                    ) : null,
                },
              ]}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
}
