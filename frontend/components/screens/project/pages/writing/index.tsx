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
import { useState } from "react";
import { toast } from "sonner";

import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DiffView } from "@/components/ui/diff-view";
import { ProjectHeader } from "@/components/screens/project/project-frame";
import { BibleBlock } from "@/components/screens/project/shared/bible-block";
import { PreflightCard } from "@/components/screens/project/shared/preflight-card";
import { severityClass, severityTone } from "@/components/screens/project/shared/severity";
import { labelForVersion } from "@/components/screens/project/shared/version-label";
import { chaptersApi, projectsApi, scenesApi } from "@/lib/api";
import { ApiError } from "@/lib/http";
import { useScopedKey } from "@/lib/use-scoped-key";

import { ContextInspector, type ContextSummaryEntry } from "./context-inspector";
import { SceneEditorCard } from "./scene-editor-card";
import { useAuditRewrite } from "./use-audit-rewrite";
import { useSceneJobs } from "./use-scene-jobs";
import { useSceneVersions } from "./use-scene-versions";

export function WritingWorkspacePage({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const chaptersKey = useScopedKey("project", projectId, "chapters");
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
    isRewriting,
  } = useSceneJobs({ projectId, activeScene });

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
    onRewriteSuccess: () => setDisplayedVersionId(null),
  });

  // === write mutation：依赖太多本地 key，保留在 page 内 ===
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
