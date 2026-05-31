"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  GitCompare,
  RefreshCw,
  Sparkles,
  Trash2,
  Wand2,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DiffView } from "@/components/ui/diff-view";
import { toPlainText } from "@/components/ui/markdown";
import { ProjectHeader } from "@/components/screens/project/project-frame";
import { BibleBlock } from "@/components/screens/project/shared/bible-block";
import { PreflightCard } from "@/components/screens/project/shared/preflight-card";
import { severityClass, severityTone } from "@/components/screens/project/shared/severity";
import { labelForVersion } from "@/components/screens/project/shared/version-label";
import { BatchJobProgressDialog } from "@/components/batch/BatchJobProgressDialog";
import {
  batchApi,
  chaptersApi,
  projectsApi,
  scenesApi,
  storyStatesApi,
  type ChapterStateRequirementType,
  type ContinuityIssue,
  type Scene,
  type StoryStateItem,
  type StoryStateMaintenanceAction,
  type StoryStateMaintenanceActionListResponse,
} from "@/lib/api";
import { ApiError } from "@/lib/http";
import { useScopedKey } from "@/lib/use-scoped-key";

import { ContextInspector, type ContextSummaryEntry } from "./context-inspector";
import { StoryStateDetailDialog } from "../outline/story-state-detail-dialog";
import { AIMaintenanceCard } from "./ai-maintenance-card";
import { AIMaintenanceReviewQueue } from "./ai-maintenance-review-queue";
import { AntiForgettingPreviewCard } from "./anti-forgetting-preview-card";
import { SceneEditorCard } from "./scene-editor-card";
import { useAuditRewrite } from "./use-audit-rewrite";
import { useSceneJobs } from "./use-scene-jobs";
import { useSceneVersions } from "./use-scene-versions";

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatBeatRange(scene: Scene) {
  const start = scene.beat_start;
  const end = scene.beat_end;
  if (!start && !end) return "";
  if (start && end && start !== end) return `beat ${start}-${end}`;
  return `beat ${start || end}`;
}

function SceneBudgetHint({ scene }: { scene: Scene }) {
  const targetWords = scene.target_words || 0;
  const beatRange = formatBeatRange(scene);
  const reason =
    scene.budget_reason?.trim() || "按章节目标字数、剧情拍点与节奏自动预算";
  const summary = scene.beat_group_summary?.trim();

  if (!targetWords && !beatRange && !summary && !reason) {
    return null;
  }

  return (
    <div className="border-b border-slate-100 px-5 py-3">
      <div className="rounded-2xl border border-amber-100 bg-gradient-to-r from-amber-50 via-orange-50/70 to-white px-3 py-2">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-bold text-amber-950">场景预算</span>
          {targetWords ? (
            <Badge tone="amber">目标 {formatNumber(targetWords)} 字</Badge>
          ) : null}
          {beatRange ? <Badge tone="orange">覆盖 {beatRange}</Badge> : null}
          <span className="text-slate-600">{reason}</span>
        </div>
        {summary ? (
          <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">
            拍点摘要：{summary}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function requirementTypeFromIssue(issueType: string): ChapterStateRequirementType {
  if (
    issueType === "state_conflict" ||
    issueType === "premature_state_use" ||
    issueType === "resolved_state_reused" ||
    issueType === "hard_constraint_violation"
  ) {
    return "must_not_conflict";
  }
  if (issueType === "forgotten_state") return "must_remember";
  return "should_reference";
}

function priorityFromSeverity(severity: string) {
  if (severity === "critical") return 100;
  if (severity === "high") return 92;
  if (severity === "medium") return 82;
  if (severity === "low") return 65;
  return 80;
}

function requirementSummaryFromIssue(issue: ContinuityIssue) {
  const fix = issue.suggested_fix?.trim();
  if (fix) return `审稿建议：${fix}`;
  return `审稿问题：${issue.description || "需要承接关键设定"}`;
}

export function WritingWorkspacePage({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const activeWriteJobIds = useRef<Set<string>>(new Set());
  const notifiedWriteJobIds = useRef<Set<string>>(new Set());
  const refreshedRewriteMaintenanceJobIds = useRef<Set<string>>(new Set());
  const chaptersKey = useScopedKey("project", projectId, "chapters");
  const preflightKey = useScopedKey("project", projectId, "preflight", "write_scene");
  const storyStatesKey = useScopedKey("project", projectId, "story-states", "issue-links");

  const { data: chapters = [] } = useQuery({
    queryKey: chaptersKey,
    queryFn: () => chaptersApi.list(projectId),
  });
  const { data: preflight } = useQuery({
    queryKey: preflightKey,
    queryFn: () => projectsApi.preflight(projectId, "write_scene"),
  });
  const { data: storyStatesResponse } = useQuery({
    queryKey: storyStatesKey,
    queryFn: () => storyStatesApi.list(projectId, { limit: 200 }),
  });
  const storyStateById = useMemo(() => {
    const entries = (storyStatesResponse?.items ?? []).map((item) => [
      item.id,
      item,
    ] as const);
    return Object.fromEntries(entries) as Record<string, StoryStateItem>;
  }, [storyStatesResponse?.items]);
  const [selectedStoryState, setSelectedStoryState] =
    useState<StoryStateItem | null>(null);

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
  const antiForgettingPreviewKey = useScopedKey(
    "project",
    projectId,
    "scene",
    activeScene?.id,
    "anti-forgetting-preview",
  );
  const {
    data: antiForgettingPreview,
    isPending: isAntiForgettingPreviewPending,
  } = useQuery({
    queryKey: antiForgettingPreviewKey,
    queryFn: () => scenesApi.antiForgettingPreview(projectId, activeScene!.id),
    enabled: !!activeScene,
  });
  const maintenanceActionsKey = useScopedKey(
    "project",
    projectId,
    "scene",
    activeScene?.id,
    "story-state-maintenance-actions",
  );
  const maintenanceReviewNeedsKey = useScopedKey(
    "project",
    projectId,
    "story-state-maintenance-review",
    "needs_review",
  );
  const maintenanceReviewSuggestedKey = useScopedKey(
    "project",
    projectId,
    "story-state-maintenance-review",
    "suggested",
  );

  // === 三个组合 hook ===
  const {
    versionsKey,
    versions,
    latestDraft,
    displayedVersion,
    setDisplayedVersionId,
    isShowingLatest,
    compareWithVersion,
    setCompareWithId,
    isComparing,
    saveVersion,
    autoSave,
    deleteVersion,
  } = useSceneVersions({ projectId, activeChapter, activeScene });

  const {
    jobsKey,
    latestSceneJob,
    isWriting,
    latestAuditJob,
    isAuditing,
    latestAuditIssueCount,
    latestRewriteJob,
    latestRewriteReview,
    isRewriting,
  } = useSceneJobs({ projectId, activeScene });

  const {
    data: maintenanceActionsResponse,
    isPending: isMaintenanceActionsPending,
  } = useQuery({
    queryKey: maintenanceActionsKey,
    queryFn: () =>
      storyStatesApi.maintenanceActions(projectId, {
        scene_id: activeScene!.id,
        limit: 20,
      }),
    enabled: !!activeScene,
    refetchInterval: isWriting || isRewriting ? 3000 : false,
  });
  const maintenanceActions = maintenanceActionsResponse?.items ?? [];
  const {
    data: maintenanceReviewNeedsResponse,
    isPending: isMaintenanceReviewNeedsPending,
  } = useQuery({
    queryKey: maintenanceReviewNeedsKey,
    queryFn: () =>
      storyStatesApi.maintenanceActions(projectId, {
        status: "needs_review",
        limit: 50,
      }),
    refetchInterval: isWriting || isRewriting ? 3000 : false,
  });
  const {
    data: maintenanceReviewSuggestedResponse,
    isPending: isMaintenanceReviewSuggestedPending,
  } = useQuery({
    queryKey: maintenanceReviewSuggestedKey,
    queryFn: () =>
      storyStatesApi.maintenanceActions(projectId, {
        status: "suggested",
        limit: 50,
      }),
    refetchInterval: isWriting || isRewriting ? 3000 : false,
  });
  const maintenanceReviewActions = useMemo(() => {
    const rows = [
      ...(maintenanceReviewNeedsResponse?.items ?? []),
      ...(maintenanceReviewSuggestedResponse?.items ?? []),
    ];
    const unique = new Map(rows.map((item) => [item.id, item]));
    return [...unique.values()].sort((a, b) =>
      (b.created_at ?? "").localeCompare(a.created_at ?? ""),
    );
  }, [maintenanceReviewNeedsResponse?.items, maintenanceReviewSuggestedResponse?.items]);
  const isMaintenanceReviewPending =
    isMaintenanceReviewNeedsPending || isMaintenanceReviewSuggestedPending;

  const syncMaintenanceActionInCache = (
    action: StoryStateMaintenanceAction,
  ) => {
    queryClient.setQueryData<StoryStateMaintenanceActionListResponse>(
      maintenanceActionsKey,
      (current) => {
        if (!current) return current;
        const exists = current.items.some((item) => item.id === action.id);
        return {
          ...current,
          items: exists
            ? current.items.map((item) => (item.id === action.id ? action : item))
            : [action, ...current.items],
        };
      },
    );
  };

  const showMaintenanceActionStateChanged = () => {
    toast.error("这条 AI 维护建议状态已变化，已刷新列表，请按最新状态操作");
    queryClient.invalidateQueries({ queryKey: maintenanceActionsKey });
    queryClient.invalidateQueries({ queryKey: maintenanceReviewNeedsKey });
    queryClient.invalidateQueries({ queryKey: maintenanceReviewSuggestedKey });
  };

  const invalidateMaintenanceActionQueries = () => {
    queryClient.invalidateQueries({ queryKey: maintenanceActionsKey });
    queryClient.invalidateQueries({ queryKey: maintenanceReviewNeedsKey });
    queryClient.invalidateQueries({ queryKey: maintenanceReviewSuggestedKey });
  };

  const {
    sceneIssues,
    sceneOpenIssues,
    openIssueCountByScene,
    issuePanelRef,
    audit,
    rewrite,
  } = useAuditRewrite({
    projectId,
    activeScene,
    jobsKey,
    versionsKey,
    scenesKey,
    latestAuditJob,
    latestAuditIssueCount,
    onRewriteSuccess: () => {
      setDisplayedVersionId(null);
      queryClient.invalidateQueries({ queryKey: maintenanceActionsKey });
    },
  });

  const createRequirementFromIssue = useMutation({
    mutationFn: ({
      issue,
      linkedState,
    }: {
      issue: ContinuityIssue;
      linkedState: StoryStateItem;
    }) => {
      if (!activeChapter) return Promise.reject(new Error("no_active_chapter"));
      return storyStatesApi.createChapterRequirement(projectId, activeChapter.id, {
        state_item_id: linkedState.id,
        requirement_type: requirementTypeFromIssue(issue.issue_type),
        summary: requirementSummaryFromIssue(issue),
        priority: priorityFromSeverity(issue.severity),
        source_issue_id: issue.id,
      });
    },
    onSuccess: () => {
      toast.success("已加入本章承接要求");
      queryClient.invalidateQueries({ queryKey: antiForgettingPreviewKey });
      queryClient.invalidateQueries({ queryKey: storyStatesKey });
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "添加承接要求失败");
    },
  });
  const rollbackMaintenanceAction = useMutation({
    mutationFn: (actionId: string) =>
      storyStatesApi.rollbackMaintenanceAction(projectId, actionId),
    onSuccess: (action) => {
      syncMaintenanceActionInCache(action);
      toast.success("已撤销 AI 维护动作");
      invalidateMaintenanceActionQueries();
      queryClient.invalidateQueries({ queryKey: storyStatesKey });
      queryClient.invalidateQueries({ queryKey: antiForgettingPreviewKey });
    },
    onError: (e: unknown) => {
      if (
        e instanceof ApiError &&
        e.message === "story_state_maintenance_action_not_applied"
      ) {
        showMaintenanceActionStateChanged();
        return;
      }
      toast.error(e instanceof ApiError ? e.message : "撤销维护动作失败");
    },
  });
  const applyMaintenanceAction = useMutation({
    mutationFn: (actionId: string) =>
      storyStatesApi.applyMaintenanceAction(projectId, actionId),
    onSuccess: (action) => {
      syncMaintenanceActionInCache(action);
      toast.success("已应用 AI 维护建议");
      invalidateMaintenanceActionQueries();
      queryClient.invalidateQueries({ queryKey: storyStatesKey });
      queryClient.invalidateQueries({ queryKey: antiForgettingPreviewKey });
    },
    onError: (e: unknown) => {
      if (
        e instanceof ApiError &&
        e.message === "story_state_maintenance_action_not_applicable"
      ) {
        showMaintenanceActionStateChanged();
        return;
      }
      toast.error(e instanceof ApiError ? e.message : "应用维护建议失败");
    },
  });

  // === write mutation：依赖太多本地 key，保留在 page 内 ===
  const write = useMutation({
    mutationFn: () => {
      if (!activeScene) {
        return Promise.reject(new Error("no_active_scene"));
      }
      return projectsApi.writeScene(projectId, activeScene.id, {
        target_words: activeScene.target_words || 1200,
      });
    },
    onSuccess: (job) => {
      activeWriteJobIds.current.add(job.id);
      toast.success("已提交场景写作任务");
      queryClient.invalidateQueries({ queryKey: jobsKey });
      queryClient.invalidateQueries({ queryKey: scenesKey });
      queryClient.invalidateQueries({ queryKey: versionsKey });
      queryClient.invalidateQueries({ queryKey: preflightKey });
      queryClient.invalidateQueries({ queryKey: antiForgettingPreviewKey });
      queryClient.invalidateQueries({ queryKey: maintenanceActionsKey });
      setDisplayedVersionId(null);
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "提交失败");
    },
  });

  // 批量写作：弹窗以 batchJobId 触发
  const [batchWriteJobId, setBatchWriteJobId] = useState<string | null>(null);
  const batchWriteCurrentChapter = useMutation({
    mutationFn: () => {
      if (!activeChapter) return Promise.reject(new Error("no_active_chapter"));
      return batchApi.writeAllScenes(projectId, {
        chapter_indices: [activeChapter.chapter_index],
        target_words: 1200,
      });
    },
    onSuccess: (job) => {
      toast.success("已启动本章批量写作");
      setBatchWriteJobId(job.id);
      queryClient.invalidateQueries({ queryKey: jobsKey });
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "提交失败");
    },
  });
  const batchWriteWholeBook = useMutation({
    mutationFn: () =>
      batchApi.writeAllScenes(projectId, { target_words: 1200 }),
    onSuccess: (job) => {
      toast.success("已启动整本批量写作");
      setBatchWriteJobId(job.id);
      queryClient.invalidateQueries({ queryKey: jobsKey });
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "提交失败");
    },
  });

  useEffect(() => {
    if (!latestSceneJob) return;
    if (latestSceneJob.status === "queued" || latestSceneJob.status === "running") {
      activeWriteJobIds.current.add(latestSceneJob.id);
      return;
    }
    if (notifiedWriteJobIds.current.has(latestSceneJob.id)) return;

    const shouldRefresh = activeWriteJobIds.current.has(latestSceneJob.id);
    notifiedWriteJobIds.current.add(latestSceneJob.id);
    if (!shouldRefresh) return;

    if (latestSceneJob.status === "succeeded") {
      queryClient.invalidateQueries({ queryKey: versionsKey });
      queryClient.invalidateQueries({ queryKey: scenesKey });
      queryClient.invalidateQueries({ queryKey: preflightKey });
      queryClient.invalidateQueries({ queryKey: antiForgettingPreviewKey });
      queryClient.invalidateQueries({ queryKey: maintenanceActionsKey });
      setDisplayedVersionId(null);
      toast.success("场景生成完成");
    } else if (latestSceneJob.status === "failed") {
      toast.error(
        latestSceneJob.error_message
          ? `场景生成失败：${latestSceneJob.error_message}`
          : "场景生成失败",
      );
    }
  }, [
    latestSceneJob,
    maintenanceActionsKey,
    preflightKey,
    queryClient,
    antiForgettingPreviewKey,
    scenesKey,
    setDisplayedVersionId,
    versionsKey,
  ]);

  useEffect(() => {
    if (latestRewriteJob?.status !== "succeeded") return;
    if (refreshedRewriteMaintenanceJobIds.current.has(latestRewriteJob.id)) return;
    refreshedRewriteMaintenanceJobIds.current.add(latestRewriteJob.id);
    queryClient.invalidateQueries({ queryKey: maintenanceActionsKey });
    queryClient.invalidateQueries({ queryKey: antiForgettingPreviewKey });
    queryClient.invalidateQueries({ queryKey: storyStatesKey });
  }, [
    antiForgettingPreviewKey,
    latestRewriteJob?.id,
    latestRewriteJob?.status,
    maintenanceActionsKey,
    queryClient,
    storyStatesKey,
  ]);

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
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => batchWriteCurrentChapter.mutate()}
            disabled={batchWriteCurrentChapter.isPending || !activeChapter}
          >
            {batchWriteCurrentChapter.isPending ? (
              <RefreshCw className="size-4 animate-spin" />
            ) : (
              <Wand2 className="size-4" />
            )}
            批量写本章
          </Button>
          <Button
            variant="secondary"
            onClick={() => batchWriteWholeBook.mutate()}
            disabled={batchWriteWholeBook.isPending}
          >
            {batchWriteWholeBook.isPending ? (
              <RefreshCw className="size-4 animate-spin" />
            ) : (
              <Wand2 className="size-4" />
            )}
            批量写整本
          </Button>
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
                          className={`flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-xs ${
                            activeScene?.id === scene.id
                              ? "border-indigo-300 bg-indigo-50"
                              : "border-slate-100"
                          }`}
                        >
                          <span className="truncate">
                            场景 {scene.scene_index} · {scene.title}
                          </span>
                          <span className="flex shrink-0 items-center gap-1">
                            {(openIssueCountByScene[scene.id] ?? 0) > 0 ? (
                              <Badge tone="rose">
                                {openIssueCountByScene[scene.id]} 问题
                              </Badge>
                            ) : null}
                            <StatusBadge status={scene.status as never} />
                          </span>
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
          {activeScene ? <SceneBudgetHint scene={activeScene} /> : null}
          {activeScene ? (
            <AntiForgettingPreviewCard
              preview={antiForgettingPreview}
              isPending={isAntiForgettingPreviewPending}
              onSelectState={setSelectedStoryState}
            />
          ) : null}
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
                  <BibleBlock title="场景目的" text={activeScene.scene_purpose || "—"} />
                  <BibleBlock title="入场状态" text={activeScene.entry_state || "—"} />
                  <BibleBlock title="退场状态" text={activeScene.exit_state || "—"} />
                  <BibleBlock title="场景目标" text={activeScene.goal || "—"} />
                  <BibleBlock title="微冲突" text={activeScene.conflict || "—"} />
                  <BibleBlock
                    title="必须包含 / 避免"
                    text={`${activeScene.must_include?.join("；") || "—"} / ${
                      activeScene.must_avoid?.join("；") || "—"
                    }`}
                  />
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
                  oldContent={toPlainText(compareWithVersion.content, compareWithVersion.content_format)}
                  newContent={toPlainText(displayedVersion.content, displayedVersion.content_format)}
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
                onSave={(content, format) => saveVersion.mutate({ content, format })}
                onAutoSave={(content, format) => autoSave.mutate({ content, format })}
                characterTarget={activeScene?.target_words || undefined}
              />
            )}
            {/* Sprint 5-A：审稿与重写面板。仅当 scene 已有 draft 且非对比模式时显示 */}
            {activeScene && displayedVersion && !isComparing ? (
              <div
                ref={issuePanelRef}
                className="scroll-mt-24 mt-4 space-y-3 border-t border-slate-100 pt-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="font-bold text-slate-950">审稿 & 问题</p>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                      <span>
                        {sceneOpenIssues.length > 0
                          ? `当前发现 ${sceneOpenIssues.length} 个待修复问题`
                          : "当前未发现连续性问题"}
                      </span>
                      {latestAuditJob ? (
                        <Badge
                          tone={
                            latestAuditJob.status === "failed"
                              ? "rose"
                              : latestAuditJob.status === "succeeded"
                                ? "green"
                                : "blue"
                          }
                        >
                          最近审稿：{latestAuditJob.status}
                          {typeof latestAuditIssueCount === "number"
                            ? ` · ${latestAuditIssueCount} 个问题`
                            : ""}
                        </Badge>
                      ) : null}
                      {latestRewriteJob ? (
                        <Badge
                          tone={
                            latestRewriteJob.status === "failed" ||
                            latestRewriteReview?.review_error
                              ? "rose"
                              : latestRewriteJob.status === "succeeded" &&
                                  latestRewriteReview?.review_passed
                                ? "green"
                                : latestRewriteJob.status === "succeeded"
                                  ? "amber"
                                  : "blue"
                          }
                        >
                          {latestRewriteJob.status === "succeeded"
                            ? latestRewriteReview?.review_error
                              ? "自动复审失败"
                              : latestRewriteReview?.review_passed
                                ? `自动复审通过 · 修复 ${
                                    latestRewriteReview.fixed_issue_count ?? 0
                                  } 条`
                                : `自动复审仍有 ${
                                    latestRewriteReview?.remaining_issue_count ??
                                    latestRewriteReview?.review_issue_count ??
                                    0
                                  } 个问题`
                            : `自动复审：${latestRewriteJob.status}`}
                        </Badge>
                      ) : null}
                    </div>
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
                    {sceneIssues.map((issue) => {
                      const linkedState = issue.story_state_item_id
                        ? storyStateById[issue.story_state_item_id]
                        : null;
                      return (
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
                            {linkedState ? (
                              <button
                                type="button"
                                onClick={() => setSelectedStoryState(linkedState)}
                                className="inline-flex items-center rounded-lg bg-blue-50 px-2 py-1 text-xs font-semibold text-blue-700 ring-1 ring-blue-200 transition hover:bg-blue-100"
                              >
                                关联关键设定：{linkedState.name}
                              </button>
                            ) : issue.story_state_item_id ? (
                              <Badge tone="slate">
                                关联关键设定：{issue.story_state_item_id}
                              </Badge>
                            ) : null}
                            {linkedState && issue.status !== "fixed" ? (
                              <Button
                                size="sm"
                                variant="secondary"
                                className="h-7 px-2 text-[11px]"
                                onClick={() =>
                                  createRequirementFromIssue.mutate({ issue, linkedState })
                                }
                                disabled={createRequirementFromIssue.isPending || !activeChapter}
                                title="把这条审稿建议固化为本章承接要求，后续写作/重写会进入防遗忘注入"
                              >
                                固化为承接要求
                              </Button>
                            ) : null}
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
                      );
                    })}
                  </ul>
                )}
              </div>
            ) : null}
          </CardContent>
        </Card>
        <div className="space-y-4">
          <AIMaintenanceReviewQueue
            actions={maintenanceReviewActions}
            chapters={chapters}
            isPending={isMaintenanceReviewPending}
            applyingActionId={
              applyMaintenanceAction.isPending
                ? (applyMaintenanceAction.variables ?? null)
                : null
            }
            storyStateById={storyStateById}
            onSelectState={setSelectedStoryState}
            onApplyAction={(actionId) => applyMaintenanceAction.mutate(actionId)}
            onFocusAction={(action) => {
              if (action.chapter_id) {
                setActiveChapterId(action.chapter_id);
              }
              setActiveSceneId(action.scene_id ?? null);
              setDisplayedVersionId(null);
              setCompareWithId(null);
            }}
          />
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
            <AIMaintenanceCard
              actions={maintenanceActions}
              isPending={isMaintenanceActionsPending}
              applyingActionId={
                applyMaintenanceAction.isPending
                  ? (applyMaintenanceAction.variables ?? null)
                  : null
              }
              rollingBackActionId={
                rollbackMaintenanceAction.isPending
                  ? (rollbackMaintenanceAction.variables ?? null)
                  : null
              }
              storyStateById={storyStateById}
              onSelectState={setSelectedStoryState}
              onApplyAction={(actionId) => applyMaintenanceAction.mutate(actionId)}
              onRollbackAction={(actionId) => rollbackMaintenanceAction.mutate(actionId)}
            />
            </CardContent>
          </Card>
        </div>
      </div>
      {batchWriteJobId ? (
        <BatchJobProgressDialog
          projectId={projectId}
          batchJobId={batchWriteJobId}
          onComplete={() => {
            queryClient.invalidateQueries({ queryKey: scenesKey });
            queryClient.invalidateQueries({ queryKey: versionsKey });
            queryClient.invalidateQueries({ queryKey: jobsKey });
            queryClient.invalidateQueries({ queryKey: preflightKey });
          }}
          onClose={() => setBatchWriteJobId(null)}
        />
      ) : null}
      {selectedStoryState ? (
        <StoryStateDetailDialog
          projectId={projectId}
          state={selectedStoryState}
          onClose={() => setSelectedStoryState(null)}
          onSaved={() => {
            queryClient.invalidateQueries({ queryKey: storyStatesKey });
            queryClient.invalidateQueries({ queryKey: antiForgettingPreviewKey });
          }}
        />
      ) : null}
    </div>
  );
}
