"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileClock, RefreshCw, Wand2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DiffView } from "@/components/ui/diff-view";
import { toPlainText } from "@/components/ui/markdown";
import { ProjectHeader } from "@/components/screens/project/project-frame";
import { severityClass, severityTone } from "@/components/screens/project/shared/severity";
import { labelForVersion } from "@/components/screens/project/shared/version-label";
import {
  chaptersApi,
  continuityIssuesApi,
  jobsApi,
  projectsApi,
  scenesApi,
  versionsApi,
  type Chapter,
  type ContinuityIssue,
  type DraftVersion,
  type Scene,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateTime, formatNumber } from "@/lib/format";
import { useProjectEvents, type ProjectEvent } from "@/lib/hooks/use-event-source";
import { ApiError } from "@/lib/http";
import { useScopedKey } from "@/lib/use-scoped-key";

const ALL = "all";

export function VersionsPage({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const [chapterFilter, setChapterFilter] = useState(ALL);
  const [sceneFilter, setSceneFilter] = useState(ALL);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [compareVersionId, setCompareVersionId] = useState<string | null>(null);
  const [onlyOpenIssues, setOnlyOpenIssues] = useState(false);

  const chaptersKey = useScopedKey("project", projectId, "chapters");
  const scenesKey = useScopedKey("project", projectId, "scenes", "all");
  const versionsKey = useScopedKey("project", projectId, "versions", "all");
  const issuesKey = useScopedKey("project", projectId, "continuity-issues");
  const jobsKey = useScopedKey("jobs");

  const { data: chapters = [] } = useQuery({
    queryKey: chaptersKey,
    queryFn: () => chaptersApi.list(projectId),
  });
  const { data: scenes = [] } = useQuery({
    queryKey: scenesKey,
    queryFn: () => scenesApi.list(projectId),
  });
  const { data: allJobs = [] } = useQuery({
    queryKey: jobsKey,
    queryFn: () => jobsApi.list(),
    refetchInterval: (query) => {
      const jobs = query.state.data ?? [];
      return jobs.some(
        (job) =>
          job.project_id === projectId &&
          ["audit_scene", "rewrite_scene"].includes(job.job_type) &&
          ["queued", "running"].includes(job.status),
      )
        ? 30000
        : false;
    },
  });

  const projectJobs = allJobs.filter((job) => job.project_id === projectId);
  const hasActiveReviewJob = projectJobs.some(
    (job) =>
      ["audit_scene", "rewrite_scene"].includes(job.job_type) &&
      ["queued", "running"].includes(job.status),
  );

  const { data: versions = [] } = useQuery({
    queryKey: versionsKey,
    queryFn: () => versionsApi.list(projectId),
    refetchInterval: hasActiveReviewJob ? 30000 : false,
  });
  const { data: issues = [] } = useQuery({
    queryKey: issuesKey,
    queryFn: () => continuityIssuesApi.list(projectId),
    refetchInterval: hasActiveReviewJob ? 30000 : false,
  });

  // SSE：把 3s 轮询替换为事件驱动 invalidate
  const handleProjectEvent = useCallback(
    (event: ProjectEvent) => {
      if (event.type.startsWith("job.")) {
        const jobType = (event.payload as { job_type?: string }).job_type;
        queryClient.invalidateQueries({ queryKey: jobsKey });
        if (jobType === "audit_scene") {
          queryClient.invalidateQueries({ queryKey: issuesKey });
        }
        if (jobType === "rewrite_scene") {
          queryClient.invalidateQueries({ queryKey: versionsKey });
          queryClient.invalidateQueries({ queryKey: issuesKey });
        }
        if (jobType === "write_scene") {
          queryClient.invalidateQueries({ queryKey: versionsKey });
        }
      }
    },
    [queryClient, jobsKey, issuesKey, versionsKey],
  );
  useProjectEvents(projectId, { onMessage: handleProjectEvent });

  const chapterById = useMemo(
    () => new Map(chapters.map((chapter) => [chapter.id, chapter])),
    [chapters],
  );
  const sceneById = useMemo(
    () => new Map(scenes.map((scene) => [scene.id, scene])),
    [scenes],
  );
  const versionsByScene = useMemo(() => groupVersionsByScene(versions), [versions]);
  const latestVersionByScene = useMemo(() => {
    const latest = new Map<string, DraftVersion>();
    versions.forEach((version) => {
      if (version.scene_id && !latest.has(version.scene_id)) {
        latest.set(version.scene_id, version);
      }
    });
    return latest;
  }, [versions]);

  const sceneOptions = useMemo(
    () =>
      chapterFilter === ALL
        ? scenes
        : scenes.filter((scene) => scene.chapter_id === chapterFilter),
    [chapterFilter, scenes],
  );

  const filteredVersions = versions.filter((version) => {
    if (chapterFilter !== ALL && version.chapter_id !== chapterFilter) return false;
    if (sceneFilter !== ALL && version.scene_id !== sceneFilter) return false;
    return true;
  });
  const selectedVersion =
    (selectedVersionId
      ? filteredVersions.find((version) => version.id === selectedVersionId)
      : undefined) ?? filteredVersions[0];
  const sameSceneVersions = selectedVersion?.scene_id
    ? (versionsByScene.get(selectedVersion.scene_id) ?? [])
    : [];
  const compareVersion = compareVersionId
    ? sameSceneVersions.find((version) => version.id === compareVersionId)
    : undefined;
  const selectedScene = selectedVersion?.scene_id
    ? sceneById.get(selectedVersion.scene_id)
    : undefined;
  const selectedChapter = selectedVersion?.chapter_id
    ? chapterById.get(selectedVersion.chapter_id)
    : selectedScene?.chapter_id
      ? chapterById.get(selectedScene.chapter_id)
      : undefined;

  const actionSceneId = selectedVersion?.scene_id ?? (sceneFilter !== ALL ? sceneFilter : null);
  const actionScene = actionSceneId ? sceneById.get(actionSceneId) : undefined;
  const actionLatestVersion = actionSceneId ? latestVersionByScene.get(actionSceneId) : undefined;
  const actionOpenIssues = actionSceneId
    ? issues.filter((issue) => issue.scene_id === actionSceneId && issue.status === "open")
    : [];
  const activeAuditJob = findLatestSceneJob(projectJobs, "audit_scene", actionSceneId);
  const activeRewriteJob = findLatestSceneJob(projectJobs, "rewrite_scene", actionSceneId);
  const isAuditing = !!activeAuditJob && ["queued", "running"].includes(activeAuditJob.status);
  const isRewriting = !!activeRewriteJob && ["queued", "running"].includes(activeRewriteJob.status);

  const visibleIssues = issues.filter((issue) => {
    if (selectedVersion?.scene_id) {
      if (issue.scene_id !== selectedVersion.scene_id) return false;
    } else {
      if (chapterFilter !== ALL && issue.chapter_id !== chapterFilter) return false;
      if (sceneFilter !== ALL && issue.scene_id !== sceneFilter) return false;
    }
    if (onlyOpenIssues && issue.status !== "open") return false;
    return true;
  });

  const latestDraftWordCount = Array.from(latestVersionByScene.values()).reduce(
    (sum, version) => sum + version.word_count,
    0,
  );
  const openIssueCount = issues.filter((issue) => issue.status === "open").length;
  const rewriteVersionCount = versions.filter(
    (version) => version.version_type === "rewrite",
  ).length;

  const audit = useMutation({
    mutationFn: () => {
      if (!actionSceneId) return Promise.reject(new Error("no_active_scene"));
      return projectsApi.auditScene(projectId, actionSceneId, { estimate_words: 500 });
    },
    onSuccess: () => {
      toast.success("已提交审稿任务");
      queryClient.invalidateQueries({ queryKey: jobsKey });
      queryClient.invalidateQueries({ queryKey: issuesKey });
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "审稿提交失败");
    },
  });

  const rewrite = useMutation({
    mutationFn: () => {
      if (!actionSceneId) return Promise.reject(new Error("no_active_scene"));
      return projectsApi.rewriteScene(projectId, actionSceneId, {
        target_words: Math.max(actionLatestVersion?.word_count ?? 1200, 800),
        estimate_words: 2000,
      });
    },
    onSuccess: () => {
      toast.success("已提交重写任务");
      queryClient.invalidateQueries({ queryKey: jobsKey });
      queryClient.invalidateQueries({ queryKey: issuesKey });
      queryClient.invalidateQueries({ queryKey: versionsKey });
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "重写提交失败");
    },
  });

  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-black text-slate-950">版本 / 审稿</h1>
          <p className="mt-1 text-sm text-slate-500">
            已接入项目版本链与连续性审稿问题，可按章节、场景查看和处理。
          </p>
        </div>
        <Link
          href={`/studio/projects/${projectId}/write`}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-slate-950 px-4 text-sm font-semibold text-white transition hover:bg-slate-800"
        >
          <FileClock className="size-4" />
          打开写作工作台
        </Link>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <MetricCard label="版本总数" value={versions.length} hint="draft_versions" />
        <MetricCard label="已有正文场景" value={latestVersionByScene.size} hint="有最新草稿" />
        <MetricCard label="最新草稿字数" value={latestDraftWordCount} hint="按场景去重" />
        <MetricCard label="待修复问题" value={openIssueCount} hint={`${rewriteVersionCount} 个重写版本`} tone="rose" />
      </div>

      <Card>
        <CardContent className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
          <label className="space-y-1 text-xs font-semibold text-slate-600">
            章节
            <select
              value={chapterFilter}
              onChange={(event) => {
                setChapterFilter(event.target.value);
                setSceneFilter(ALL);
                setSelectedVersionId(null);
                setCompareVersionId(null);
              }}
              className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-900"
            >
              <option value={ALL}>全部章节</option>
              {chapters.map((chapter) => (
                <option key={chapter.id} value={chapter.id}>
                  第 {chapter.chapter_index} 章 · {chapter.title}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-xs font-semibold text-slate-600">
            场景
            <select
              value={sceneFilter}
              onChange={(event) => {
                setSceneFilter(event.target.value);
                setSelectedVersionId(null);
                setCompareVersionId(null);
              }}
              className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-900"
            >
              <option value={ALL}>全部场景</option>
              {sceneOptions.map((scene) => (
                <option key={scene.id} value={scene.id}>
                  场景 {scene.scene_index} · {scene.title}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-end gap-2 pb-2 text-sm font-semibold text-slate-700">
            <input
              type="checkbox"
              checked={onlyOpenIssues}
              onChange={(event) => setOnlyOpenIssues(event.target.checked)}
              className="size-4 rounded border-slate-300"
            />
            只看待修复问题
          </label>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <Card className="self-start">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>版本历史</CardTitle>
            <Badge tone="slate">{filteredVersions.length}</Badge>
          </CardHeader>
          <CardContent className="max-h-[760px] space-y-2 overflow-y-auto">
            {versions.length === 0 ? (
              <EmptyState text="暂无版本。先在写作工作台生成场景正文。" />
            ) : filteredVersions.length === 0 ? (
              <EmptyState text="当前筛选条件下没有版本。" />
            ) : (
              filteredVersions.map((version) => {
                const scene = version.scene_id ? sceneById.get(version.scene_id) : undefined;
                const chapter = version.chapter_id
                  ? chapterById.get(version.chapter_id)
                  : scene?.chapter_id
                    ? chapterById.get(scene.chapter_id)
                    : undefined;
                const sceneVersions = version.scene_id
                  ? (versionsByScene.get(version.scene_id) ?? [])
                  : filteredVersions;
                const isActive = selectedVersion?.id === version.id;
                return (
                  <button
                    key={version.id}
                    type="button"
                    onClick={() => {
                      setSelectedVersionId(version.id);
                      setCompareVersionId(null);
                    }}
                    className={cn(
                      "w-full rounded-2xl border p-3 text-left text-sm transition",
                      isActive
                        ? "border-indigo-300 bg-indigo-50 shadow-sm"
                        : "border-slate-200 hover:bg-slate-50",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-black text-slate-950">
                        {labelForVersion(sceneVersions, version.id)}
                      </span>
                      <Badge tone={versionTypeTone(version.version_type)}>
                        {version.version_type}
                      </Badge>
                    </div>
                    <p className="mt-2 truncate text-xs font-semibold text-slate-700">
                      {formatChapterScene(chapter, scene)}
                    </p>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                      <span>{formatNumber(version.word_count)} 字</span>
                      <StatusBadge status={version.status} />
                      <span>{version.created_at ? formatDateTime(version.created_at) : "—"}</span>
                    </div>
                  </button>
                );
              })
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <VersionDetailCard
            version={selectedVersion}
            versions={sameSceneVersions}
            compareVersion={compareVersion}
            compareVersionId={compareVersion?.id ?? ""}
            chapter={selectedChapter}
            scene={selectedScene}
            latestVersion={actionLatestVersion}
            actionScene={actionScene}
            openIssueCount={actionOpenIssues.length}
            isAuditing={isAuditing || audit.isPending}
            isRewriting={isRewriting || rewrite.isPending}
            canAudit={!!actionSceneId && !!actionLatestVersion}
            canRewrite={!!actionSceneId && !!actionLatestVersion && actionOpenIssues.length > 0}
            onCompareChange={setCompareVersionId}
            onAudit={() => audit.mutate()}
            onRewrite={() => rewrite.mutate()}
          />

          <IssuesCard
            title={selectedVersion?.scene_id ? "当前场景审稿问题" : "审稿问题"}
            issues={visibleIssues}
            chapterById={chapterById}
            sceneById={sceneById}
          />
        </div>
      </div>
    </div>
  );
}

type VersionDetailCardProps = {
  version?: DraftVersion;
  versions: DraftVersion[];
  compareVersion?: DraftVersion;
  compareVersionId: string;
  chapter?: Chapter;
  scene?: Scene;
  latestVersion?: DraftVersion;
  actionScene?: Scene;
  openIssueCount: number;
  isAuditing: boolean;
  isRewriting: boolean;
  canAudit: boolean;
  canRewrite: boolean;
  onCompareChange: (versionId: string | null) => void;
  onAudit: () => void;
  onRewrite: () => void;
};

function VersionDetailCard({
  version,
  versions,
  compareVersion,
  compareVersionId,
  chapter,
  scene,
  latestVersion,
  actionScene,
  openIssueCount,
  isAuditing,
  isRewriting,
  canAudit,
  canRewrite,
  onCompareChange,
  onAudit,
  onRewrite,
}: VersionDetailCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div>
          <CardTitle>版本详情</CardTitle>
          {version ? (
            <p className="mt-1 text-xs text-slate-500">
              {formatChapterScene(chapter, scene)}
            </p>
          ) : null}
        </div>
        {version ? (
          <div className="flex flex-wrap justify-end gap-2">
            <Badge tone={versionTypeTone(version.version_type)}>{version.version_type}</Badge>
            <StatusBadge status={version.status} />
          </div>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-4">
        {!version ? (
          <EmptyState text="请选择一个版本查看正文。" />
        ) : (
          <>
            <div className="grid gap-3 rounded-2xl bg-slate-50 p-4 text-sm md:grid-cols-4">
              <Meta label="版本" value={labelForVersion(versions, version.id)} />
              <Meta label="字数" value={`${formatNumber(version.word_count)} 字`} />
              <Meta label="创建时间" value={version.created_at ? formatDateTime(version.created_at) : "—"} />
              <Meta label="父版本" value={version.parent_version_id ? "有" : "无"} />
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 p-3">
              <div>
                <p className="text-sm font-bold text-slate-950">
                  {actionScene ? `场景 ${actionScene.scene_index} · ${actionScene.title}` : "请选择场景"}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  审稿和重写始终作用于该场景的最新版本
                  {latestVersion && latestVersion.id !== version.id ? "，当前预览为历史版本" : ""}。
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  onClick={onAudit}
                  disabled={!canAudit || isAuditing}
                  title={!canAudit ? "该场景还没有草稿版本" : "对最新版本触发审稿"}
                >
                  {isAuditing ? <RefreshCw className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
                  审稿
                </Button>
                <Button
                  onClick={onRewrite}
                  disabled={!canRewrite || isRewriting}
                  title={openIssueCount === 0 ? "没有待修复问题" : "基于待修复问题重写"}
                >
                  {isRewriting ? <RefreshCw className="size-4 animate-spin" /> : <Wand2 className="size-4" />}
                  重写并修复
                </Button>
              </div>
            </div>

            <label className="block space-y-1 text-xs font-semibold text-slate-600">
              对比版本
              <select
                value={compareVersionId}
                onChange={(event) => onCompareChange(event.target.value || null)}
                className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-900"
              >
                <option value="">不对比，直接预览正文</option>
                {versions
                  .filter((candidate) => candidate.id !== version.id)
                  .map((candidate) => (
                    <option key={candidate.id} value={candidate.id}>
                      {labelForVersion(versions, candidate.id)} · {candidate.version_type} · {formatNumber(candidate.word_count)} 字
                    </option>
                  ))}
              </select>
            </label>

            {compareVersion ? (
              <DiffView
                oldContent={toPlainText(compareVersion.content, compareVersion.content_format)}
                newContent={toPlainText(version.content, version.content_format)}
                oldLabel={labelForVersion(versions, compareVersion.id)}
                newLabel={labelForVersion(versions, version.id)}
              />
            ) : (
              <div className="max-h-[560px] overflow-y-auto rounded-2xl border border-slate-200 bg-white p-5">
                {version.content ? (
                  <pre className="whitespace-pre-wrap text-sm leading-7 text-slate-800">
                    {toPlainText(version.content, version.content_format)}
                  </pre>
                ) : (
                  <p className="text-sm text-slate-500">该版本内容为空。</p>
                )}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

type IssuesCardProps = {
  title: string;
  issues: ContinuityIssue[];
  chapterById: Map<string, Chapter>;
  sceneById: Map<string, Scene>;
};

function IssuesCard({ title, issues, chapterById, sceneById }: IssuesCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>{title}</CardTitle>
        <Badge tone={issues.some((issue) => issue.status === "open") ? "rose" : "slate"}>
          {issues.length}
        </Badge>
      </CardHeader>
      <CardContent>
        {issues.length === 0 ? (
          <EmptyState text="当前范围暂无审稿问题。" />
        ) : (
          <ul className="space-y-2">
            {issues.map((issue) => {
              const scene = issue.scene_id ? sceneById.get(issue.scene_id) : undefined;
              const chapter = issue.chapter_id
                ? chapterById.get(issue.chapter_id)
                : scene?.chapter_id
                  ? chapterById.get(scene.chapter_id)
                  : undefined;
              return (
                <li
                  key={issue.id}
                  className={cn(
                    "rounded-2xl border p-4 text-sm",
                    issue.status === "fixed" ? "border-emerald-200 bg-emerald-50/40" : severityClass(issue.severity),
                  )}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={severityTone(issue.severity)}>{issue.severity}</Badge>
                    <Badge tone="slate">{issue.issue_type}</Badge>
                    <Badge tone={issue.status === "fixed" ? "green" : "amber"}>{issue.status}</Badge>
                    <span className="text-xs text-slate-500">
                      {formatChapterScene(chapter, scene)}
                    </span>
                  </div>
                  <p className="mt-3 font-semibold text-slate-950">{issue.description}</p>
                  {issue.suggested_fix ? (
                    <p className="mt-2 text-slate-600">建议：{issue.suggested_fix}</p>
                  ) : null}
                  {issue.created_at ? (
                    <p className="mt-2 text-xs text-slate-500">{formatDateTime(issue.created_at)}</p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function MetricCard({
  label,
  value,
  hint,
  tone = "slate",
}: {
  label: string;
  value: number;
  hint: string;
  tone?: "slate" | "rose";
}) {
  return (
    <Card>
      <CardContent>
        <p className="text-xs font-semibold text-slate-500">{label}</p>
        <p className={cn("mt-2 text-3xl font-black", tone === "rose" ? "text-rose-600" : "text-slate-950")}>
          {formatNumber(value)}
        </p>
        <p className="mt-1 text-xs text-slate-500">{hint}</p>
      </CardContent>
    </Card>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-semibold text-slate-500">{label}</p>
      <p className="mt-1 truncate font-bold text-slate-950">{value}</p>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <p className="py-8 text-center text-sm text-slate-500">{text}</p>;
}

function groupVersionsByScene(versions: DraftVersion[]) {
  const grouped = new Map<string, DraftVersion[]>();
  versions.forEach((version) => {
    const key = version.scene_id ?? "project";
    grouped.set(key, [...(grouped.get(key) ?? []), version]);
  });
  return grouped;
}

function findLatestSceneJob(
  jobs: { job_type: string; status: string; input_payload?: Record<string, unknown> | null }[],
  jobType: string,
  sceneId: string | null,
) {
  if (!sceneId) return undefined;
  return jobs.find(
    (job) =>
      job.job_type === jobType &&
      (job.input_payload as { scene_id?: string } | null | undefined)?.scene_id === sceneId,
  );
}

function formatChapterScene(chapter?: Chapter, scene?: Scene) {
  const chapterLabel = chapter ? `第 ${chapter.chapter_index} 章` : "未绑定章节";
  const sceneLabel = scene ? `场景 ${scene.scene_index} · ${scene.title}` : "未绑定场景";
  return `${chapterLabel} / ${sceneLabel}`;
}

function versionTypeTone(type: string): "slate" | "blue" | "green" | "amber" | "violet" {
  switch (type) {
    case "user":
      return "violet";
    case "rewrite":
      return "green";
    case "autosave":
      return "amber";
    case "draft":
      return "blue";
    default:
      return "slate";
  }
}
