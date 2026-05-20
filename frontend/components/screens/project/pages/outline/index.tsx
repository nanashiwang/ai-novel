"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Sparkles, Wand2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { ProjectHeader } from "@/components/screens/project/project-frame";
import { BibleBlock } from "@/components/screens/project/shared/bible-block";
import {
  chaptersApi,
  type GenerationJob,
  jobsApi,
  projectsApi,
  scenesApi,
} from "@/lib/api";
import { ApiError } from "@/lib/http";
import { useScopedKey } from "@/lib/use-scoped-key";

export function OutlinePage({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const projectKey = useScopedKey("project", projectId);
  const chaptersKey = useScopedKey("project", projectId, "chapters");
  const jobsKey = useScopedKey("jobs");

  const { data: chapters = [] } = useQuery({
    queryKey: chaptersKey,
    queryFn: () => chaptersApi.list(projectId),
  });
  const { data: project } = useQuery({
    queryKey: projectKey,
    queryFn: () => projectsApi.get(projectId),
  });

  // 找出本项目的 generate_outline 任务最近一条（jobs.list 默认 created_at desc）。
  // 用于驱动生成按钮的 loading 态与轮询刷新。
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
      return projectActive || waitingForChapters ? 1500 : false;
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
