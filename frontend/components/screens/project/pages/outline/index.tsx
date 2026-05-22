"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Sparkles, Wand2 } from "lucide-react";
import { useCallback, useState } from "react";
import { toast } from "sonner";

import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { ProjectHeader } from "@/components/screens/project/project-frame";
import { BibleBlock } from "@/components/screens/project/shared/bible-block";
import {
  type Chapter,
  chaptersApi,
  type GenerationJob,
  type RevisionTargetType,
  jobsApi,
  projectsApi,
  scenesApi,
} from "@/lib/api";
import { useProjectEvents, type ProjectEvent } from "@/lib/hooks/use-event-source";
import { ApiError } from "@/lib/http";
import { useScopedKey } from "@/lib/use-scoped-key";
import { RevisionCopilotDrawer } from "../bible/revision-copilot-drawer";

type RevisionDrawerConfig = {
  scope: string;
  targetType?: RevisionTargetType | null;
  targetId?: string | null;
  title: string;
  description?: string;
  starterPrompts: string[];
};

export function OutlinePage({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const projectKey = useScopedKey("project", projectId);
  const chaptersKey = useScopedKey("project", projectId, "chapters");
  const jobsKey = useScopedKey("jobs");

  const { data: chapterRows = [] } = useQuery({
    queryKey: chaptersKey,
    queryFn: () => chaptersApi.list(projectId),
  });
  const chapters = [...chapterRows].sort(
    (a, b) => (a.chapter_index ?? 0) - (b.chapter_index ?? 0),
  );
  const { data: project } = useQuery({
    queryKey: projectKey,
    queryFn: () => projectsApi.get(projectId),
  });

  // jobs 列表保留 30s 兜底轮询：SSE 接管实时状态变化后，兜底确保跨页签同步
  const { data: jobs = [] } = useQuery({
    queryKey: jobsKey,
    queryFn: () => jobsApi.list(),
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
      return projectActive || waitingForChapters ? 30000 : false;
    },
  });
  const latestJob = jobs.find(
    (j) => j.project_id === projectId && j.job_type === "generate_outline",
  );
  const isGenerating = latestJob?.status === "queued" || latestJob?.status === "running";
  const targetChapterCount = project?.target_chapter_count ?? 0;
  const shouldAppendOutline =
    chapters.length > 0 && targetChapterCount > chapters.length;
  const outlineProgress =
    targetChapterCount > 0
      ? `已生成 ${chapters.length}/${targetChapterCount} 章`
      : chapters.length > 0
        ? `已生成 ${chapters.length} 章`
        : "未生成";
  const generateOutlineLabel = isGenerating
    ? "生成中"
    : chapters.length === 0
      ? "启动生成"
      : shouldAppendOutline
        ? `补全至 ${targetChapterCount} 章`
        : "重新生成大纲";

  const generate = useMutation({
    mutationFn: () =>
      projectsApi.generateOutline(projectId, {
        target_chapters: targetChapterCount || undefined,
        estimate_words: 3000,
        force_regenerate: chapters.length > 0 && !shouldAppendOutline,
      }),
    onSuccess: () => {
      toast.success(
        shouldAppendOutline ? "已提交后续章节大纲补全任务" : "已提交章节大纲生成任务",
      );
      queryClient.invalidateQueries({ queryKey: chaptersKey });
      queryClient.invalidateQueries({ queryKey: projectKey });
      queryClient.invalidateQueries({ queryKey: jobsKey });
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "提交失败");
    },
  });

  const [activeId, setActiveId] = useState<string | null>(null);
  const [sceneCountMode, setSceneCountMode] = useState<"auto" | "manual">("auto");
  const [manualSceneCount, setManualSceneCount] = useState(3);
  const [revisionConfig, setRevisionConfig] = useState<RevisionDrawerConfig | null>(null);
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

  const invalidateRevisionTargets = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: chaptersKey });
    queryClient.invalidateQueries({ queryKey: scenesKey });
    queryClient.invalidateQueries({ queryKey: jobsKey });
    queryClient.invalidateQueries({ queryKey: projectKey });
  }, [queryClient, chaptersKey, scenesKey, jobsKey, projectKey]);

  const openOutlineRevision = () => {
    setRevisionConfig({
      scope: "outline",
      targetType: null,
      title: "优化章节大纲",
      description: "重点优化未写章节的标题、摘要、目标、冲突和钩子；已有场景的章节不会自动改。",
      starterPrompts: [
        "请优化未写章节的节奏、冲突和钩子，不创建、不删除、不重排章节；如影响人物或剧情线，请给出同组联动提案。",
        "请检查当前大纲是否有节奏断层或重复冲突，只给出可安全应用到无场景章节的修改。",
      ],
    });
  };

  const openChapterRevision = (chapter: Chapter) => {
    setRevisionConfig({
      scope: "chapter",
      targetType: "chapter",
      targetId: chapter.id,
      title: `优化第 ${chapter.chapter_index} 章`,
      description: "只优化当前章节大纲；如果该章已有场景，应用时会被后端拒绝，避免破坏正文链路。",
      starterPrompts: [
        "请优化这一章的标题、摘要、章节目标、核心冲突和结尾钩子；如影响人物或剧情线，请给出同组联动提案。",
        "请检查这一章是否承接前后章节，并补强情绪钩子和剧情推进。",
      ],
    });
  };

  // SSE：监听项目任务状态变化（替代 1.5s 轮询）
  const handleProjectEvent = useCallback(
    (event: ProjectEvent) => {
      if (event.type.startsWith("job.")) {
        const jobType = (event.payload as { job_type?: string }).job_type;
        queryClient.invalidateQueries({ queryKey: jobsKey });
        if (jobType === "generate_outline") {
          queryClient.invalidateQueries({ queryKey: chaptersKey });
          queryClient.invalidateQueries({ queryKey: projectKey });
        } else if (jobType === "generate_scene_plan") {
          queryClient.invalidateQueries({ queryKey: scenesKey });
        }
      }
    },
    [queryClient, jobsKey, chaptersKey, projectKey, scenesKey],
  );
  useProjectEvents(projectId, { onMessage: handleProjectEvent });

  const generateScenes = useMutation({
    mutationFn: () => {
      if (!active) {
        return Promise.reject(new Error("no_active_chapter"));
      }
      return projectsApi.generateScenePlan(projectId, active.id, {
        scenes_per_chapter: sceneCountMode === "manual" ? manualSceneCount : null,
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
              {outlineProgress}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-slate-50 p-4">
            <div>
              <p className="font-bold text-slate-950">Sprint 2 大纲闭环</p>
              <p className="text-sm text-slate-500">
                {shouldAppendOutline
                  ? "当前少于项目目标章节数，点击补全会只追加缺失的后续章节。"
                  : "调用模型规划三幕推进，每章产出标题、摘要、目标、冲突、结尾钩子。"}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                onClick={openOutlineRevision}
                disabled={chapters.length === 0}
              >
                <Sparkles className="size-4" /> AI 优化大纲
              </Button>
              <Button
                onClick={() => generate.mutate()}
                disabled={generate.isPending || isGenerating}
              >
                {isGenerating ? (
                  <RefreshCw className="size-4 animate-spin" />
                ) : (
                  <Sparkles className="size-4" />
                )}
                {generateOutlineLabel}
              </Button>
            </div>
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
              <div className="flex items-center gap-2">
                <Badge tone={scenes.length > 0 ? "amber" : "violet"}>
                  {scenes.length > 0 ? "已有场景，自动应用会受限" : "可安全优化"}
                </Badge>
                <Button size="sm" variant="secondary" onClick={() => openChapterRevision(active)}>
                  <Sparkles className="size-3.5" /> AI 优化
                </Button>
              </div>
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
                  {
                    key: "purpose",
                    header: "目的",
                    render: (row) => row.scene_purpose || row.goal || "—",
                  },
                  {
                    key: "state",
                    header: "承接",
                    render: (row) =>
                      row.entry_state || row.exit_state
                        ? `${row.entry_state || "—"} → ${row.exit_state || "—"}`
                        : "—",
                  },
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
                <div className="flex flex-wrap items-center gap-2">
                  <label className="text-xs font-semibold text-slate-600">
                    场景数
                    <select
                      value={sceneCountMode === "auto" ? "auto" : String(manualSceneCount)}
                      onChange={(event) => {
                        if (event.target.value === "auto") {
                          setSceneCountMode("auto");
                        } else {
                          setSceneCountMode("manual");
                          setManualSceneCount(Number(event.target.value));
                        }
                      }}
                      className="ml-2 h-9 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800"
                    >
                      <option value="auto">AI 自动判断</option>
                      {[1, 2, 3, 4, 5, 6, 7, 8].map((count) => (
                        <option key={count} value={count}>
                          {count} 个
                        </option>
                      ))}
                    </select>
                  </label>
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
              </div>
            </CardContent>
          </Card>
        ) : null}
      </div>
      {revisionConfig ? (
        <RevisionCopilotDrawer
          projectId={projectId}
          scope={revisionConfig.scope}
          targetType={revisionConfig.targetType}
          targetId={revisionConfig.targetId}
          title={revisionConfig.title}
          description={revisionConfig.description}
          starterPrompts={revisionConfig.starterPrompts}
          onClose={() => setRevisionConfig(null)}
          onApplied={invalidateRevisionTargets}
        />
      ) : null}
    </div>
  );
}
