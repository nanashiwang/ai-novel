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
  Network,
  RefreshCw,
  Sparkles,
  TimerReset,
  Users,
  Wand2,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ProjectHeader } from "./project-frame";
import { ActionCard } from "@/components/ui/action-card";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { EditorMock } from "@/components/ui/editor-mock";
import { ProgressBar } from "@/components/ui/progress";
import {
  chaptersApi,
  charactersApi,
  exportsApi,
  jobsApi,
  projectsApi,
  scenesApi,
  worldItemsApi,
} from "@/lib/api";
import type { Bible, BibleCharacter, BiblePlotThread, BibleWorldItem } from "@/lib/api";
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

type Chapter = {
  id: string;
  chapter_index: number;
  title: string;
  summary: string;
  goal: string;
  conflict: string;
  ending_hook: string;
  status: string;
};

type Scene = {
  id: string;
  scene_index: number;
  title: string;
  location: string;
  goal: string;
  status: string;
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

type ExportFileRow = {
  id: string;
  project_id: string;
  export_type: string;
  file_url: string;
  status: string;
  created_at: string;
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
export function BiblePage({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const projectKey = useScopedKey("project", projectId);
  const bibleKey = useScopedKey("project", projectId, "bible");
  const charactersKey = useScopedKey("project", projectId, "characters");
  const worldItemsKey = useScopedKey("project", projectId, "world-items");
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
  const latestJob = bible?.latest_job;
  const isGenerating = latestJob?.status === "queued" || latestJob?.status === "running";

  const generate = useMutation({
    mutationFn: () =>
      projectsApi.generateBible(projectId, {
        estimate_words: 2000,
        force_regenerate: !bible?.spec,
      }),
    onSuccess: () => {
      toast.success("已提交故事圣经生成任务");
      queryClient.invalidateQueries({ queryKey: bibleKey });
      queryClient.invalidateQueries({ queryKey: projectKey });
      queryClient.invalidateQueries({ queryKey: charactersKey });
      queryClient.invalidateQueries({ queryKey: worldItemsKey });
      queryClient.invalidateQueries({ queryKey: jobsKey });
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "提交失败");
    },
  });

  const spec = bible?.spec;
  const characters = bible?.characters ?? [];
  const worldItems = bible?.world_items ?? [];
  const plotThreads = bible?.plot_threads ?? [];

  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>故事圣经 Story Bible</CardTitle>
            <p className="mt-1 text-sm text-slate-500">生成后会同步写入设定、人物、世界观与主线。</p>
          </div>
          <div className="flex items-center gap-2">
            {latestJob ? <StatusBadge status={latestJob.status as never} /> : null}
            <Badge tone={spec ? "blue" : "slate"}>{spec ? "已生成" : "未生成"}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-slate-50 p-4">
            <div>
              <p className="font-bold text-slate-950">Sprint 1 生成闭环</p>
              <p className="text-sm text-slate-500">
                提交任务后会预留额度，调用模型，完成后自动展示结果。
              </p>
            </div>
            <Button onClick={() => generate.mutate()} disabled={generate.isPending || isGenerating}>
              {isGenerating ? <RefreshCw className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
              {spec ? "重新生成" : "启动生成"}
            </Button>
          </div>
          {latestJob ? (
            <div className="grid gap-3 md:grid-cols-3">
              <BibleBlock title="任务类型" text={latestJob.job_type} />
              <BibleBlock title="额度" text={`${latestJob.consumed_quota}/${latestJob.reserved_quota}`} />
              <BibleBlock title="Workflow" text={latestJob.workflow_id ?? "—"} />
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
              <Badge tone="violet">{spec.genre || "未分类"}</Badge>
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
              <CardHeader>
                <CardTitle>主要人物</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3 md:grid-cols-2">
                {characters.length === 0 ? (
                  <p className="text-sm text-slate-500">暂无人物。</p>
                ) : (
                  characters.map((character: BibleCharacter) => (
                    <BibleItem
                      key={character.id}
                      title={character.name}
                      badge={character.role}
                      text={[character.description, character.motivation, character.arc]
                        .filter(Boolean)
                        .join(" / ")}
                    />
                  ))
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>剧情线</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {plotThreads.length === 0 ? (
                  <p className="text-sm text-slate-500">暂无剧情线。</p>
                ) : (
                  plotThreads.map((thread: BiblePlotThread) => (
                    <BibleItem
                      key={thread.id}
                      title={thread.title}
                      badge={`${thread.thread_type} · ${thread.status}`}
                      text={thread.description}
                    />
                  ))
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>世界观条目</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {worldItems.length === 0 ? (
                <p className="text-sm text-slate-500">暂无世界观条目。</p>
              ) : (
                worldItems.map((item: BibleWorldItem) => (
                  <BibleItem
                    key={item.id}
                    title={item.name}
                    badge={item.is_hard_rule ? "硬规则" : item.importance}
                    text={item.description}
                  />
                ))
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
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
  const { data: chapters = [] } = useQuery({
    queryKey: useScopedKey("project", projectId, "chapters"),
    queryFn: () => chaptersApi.list(projectId) as Promise<Chapter[]>,
  });
  const [activeId, setActiveId] = useState<string | null>(null);
  const active = chapters.find((c) => c.id === activeId) ?? chapters[0];

  const { data: scenes = [] } = useQuery({
    queryKey: useScopedKey("project", projectId, "scenes", active?.id),
    queryFn: () => scenesApi.list(projectId, active?.id) as Promise<Scene[]>,
    enabled: !!active,
  });

  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
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
                    场景生成会创建 generation_job 并预留额度。
                  </p>
                </div>
                <Button onClick={() => toast.info("场景生成接口待接入")}>
                  <Wand2 className="size-4" /> 生成场景正文
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
export function WritingWorkspacePage({ projectId }: { projectId: string }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm text-slate-500">工作台 / 项目 / {projectId} / 写作</p>
          <h1 className="text-2xl font-black text-slate-950">写作工作台</h1>
          <p className="mt-1 text-sm text-slate-500">
            最小生成单位：scene。从大纲页选择章节场景再进入此页。
          </p>
        </div>
        <Button onClick={() => toast.info("scene 生成接口待对接")}>
          <Sparkles className="size-4" /> 生成当前场景
        </Button>
      </div>
      <div className="grid min-h-[420px] gap-4 xl:grid-cols-[280px_minmax(520px,1fr)_340px]">
        <Card>
          <CardHeader>
            <CardTitle>章节 / 场景</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-500">
              选择章节后会列出场景。当前展示固定占位，等接入 scenes API 后会自动加载。
            </p>
          </CardContent>
        </Card>
        <EditorMock />
        <Card>
          <CardHeader>
            <CardTitle>Context Builder</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-500">
              会合并 Story Bible、人物状态、世界观召回、前文摘要交给 ModelGateway。
            </p>
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
                  render: (row) =>
                    row.status === "queued" || row.status === "running" ? (
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={() => cancel.mutate(row.id)}
                        disabled={cancel.isPending}
                      >
                        取消
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
  const { data: files = [] } = useQuery({
    queryKey: useScopedKey("project", projectId, "exports"),
    queryFn: () => exportsApi.list(projectId) as Promise<ExportFileRow[]>,
  });
  const create = useMutation({
    mutationFn: (export_type: string) => exportsApi.create(projectId, export_type),
    onSuccess: () => {
      toast.success("已创建导出任务");
      queryClient.invalidateQueries({ queryKey: ["org"] });
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "创建失败"),
  });

  const formats = ["markdown", "txt", "docx", "epub", "pdf"];

  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <div className="grid gap-4 md:grid-cols-5">
        {formats.map((format) => (
          <Card key={format}>
            <CardContent className="text-center">
              <FileArchive className="mx-auto size-9 text-indigo-600" />
              <h3 className="mt-3 font-black uppercase text-slate-950">{format}</h3>
              <Button
                className="mt-4 w-full"
                size="sm"
                onClick={() => create.mutate(format)}
                disabled={create.isPending}
              >
                开始导出
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
                { key: "time", header: "时间", render: (row) => formatDateTime(row.created_at) },
                {
                  key: "download",
                  header: "操作",
                  render: (row) =>
                    row.file_url ? (
                      <a href={row.file_url} target="_blank" rel="noreferrer">
                        <Button size="sm" variant="secondary">
                          <Download className="size-4" /> 下载
                        </Button>
                      </a>
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
