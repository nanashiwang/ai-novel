"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Eye,
  RefreshCw,
  Search,
  Sparkles,
  Wand2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { ProjectHeader } from "@/components/screens/project/project-frame";
import { BibleBlock } from "@/components/screens/project/shared/bible-block";
import { BatchJobProgressDialog } from "@/components/batch/BatchJobProgressDialog";
import {
  batchApi,
  type ChapterStateRequirement,
  type Chapter,
  chaptersApi,
  type GenerationJob,
  type RevisionTargetType,
  type StoryStateItem,
  jobsApi,
  projectsApi,
  scenesApi,
  storyStatesApi,
} from "@/lib/api";
import { useProjectEvents, type ProjectEvent } from "@/lib/hooks/use-event-source";
import { ApiError } from "@/lib/http";
import { useScopedKey } from "@/lib/use-scoped-key";
import { RevisionCopilotDrawer } from "../bible/revision-copilot-drawer";
import {
  ChapterRequirementListDialog,
  StoryStateDetailDialog,
  StoryStateListDialog,
} from "./story-state-detail-dialog";

type RevisionDrawerConfig = {
  scope: string;
  targetType?: RevisionTargetType | null;
  targetId?: string | null;
  title: string;
  description?: string;
  starterPrompts: string[];
};

type OutlineFilter = "all" | "no-scenes" | "has-scenes" | "written" | "safe-optimize";
type OutlineQuickView = "all" | "current-group" | "safe-optimize" | "written";
type BadgeTone = "slate" | "blue" | "green" | "amber" | "rose" | "violet" | "orange";

const CHAPTER_GROUP_SIZE = 50;
const WRITTEN_SCENE_STATUSES = new Set(["drafted", "audited", "rewritten", "approved"]);

const STORY_STATE_TYPE_LABEL: Record<string, string> = {
  skill: "能力",
  artifact: "器物",
  identity: "身份",
  grudge: "恩怨",
  foreshadow: "伏笔",
  oath: "誓约",
};

const STORY_STATE_ENTITY_LABEL: Record<string, string> = {
  character: "人物",
  artifact: "器物",
  plot_thread: "剧情线",
  relationship: "关系",
  world_rule: "世界规则",
};

const STORY_STATE_STATUS_LABEL: Record<string, string> = {
  active: "活跃",
  hidden: "隐藏",
  damaged: "已损坏",
  resolved: "已解决",
  consumed: "已消耗",
  inactive: "非活跃",
};

const REQUIREMENT_TYPE_LABEL: Record<string, string> = {
  must_remember: "必须承接",
  must_not_conflict: "禁止冲突",
  should_reference: "建议呼应",
  candidate_payoff: "可回收",
};

function getRequirementTone(type: string): BadgeTone {
  if (type === "must_not_conflict") return "rose";
  if (type === "must_remember") return "amber";
  if (type === "candidate_payoff") return "violet";
  return "blue";
}

function getRequirementOriginTone(requirement: ChapterStateRequirement): BadgeTone {
  if (requirement.origin_type === "previous_chapter_carryover") return "green";
  if (requirement.origin_type === "current_chapter_extract") return "blue";
  if (requirement.origin_type === "manual") return "orange";
  if (requirement.origin_type === "backfill") return "violet";
  return "slate";
}

function formatRequirementOriginLabel(requirement: ChapterStateRequirement): string {
  if (requirement.origin_type === "previous_chapter_carryover") {
    return requirement.source_chapter_index != null
      ? `来自第 ${requirement.source_chapter_index} 章`
      : "来自前文";
  }
  if (requirement.origin_type === "current_chapter_extract") return "本章提取";
  if (requirement.origin_type === "manual") return "人工添加";
  if (requirement.origin_type === "backfill") return "历史补全";
  return "来源未知";
}

function getStoryStateTone(state: StoryStateItem): BadgeTone {
  if (state.is_hard_constraint) return "rose";
  if (state.state_type === "foreshadow") return "violet";
  if (state.state_type === "skill") return "green";
  if (state.state_type === "grudge") return "amber";
  return "slate";
}

function getStoryStateStatusTone(status: string): BadgeTone {
  if (status === "active") return "green";
  if (status === "damaged" || status === "consumed") return "amber";
  if (status === "resolved") return "blue";
  return "slate";
}

function storyStateMeta(state: StoryStateItem) {
  const entityLabel = STORY_STATE_ENTITY_LABEL[state.entity_type] ?? state.entity_type;
  const typeLabel = STORY_STATE_TYPE_LABEL[state.state_type] ?? state.state_type;
  return `${entityLabel} · ${typeLabel} · 优先级 ${state.priority}`;
}

function ChapterRequirementPanel({
  items,
  onSelectState,
  onOpenList,
}: {
  items: Array<{ requirement: ChapterStateRequirement; state: StoryStateItem | null }>;
  onSelectState: (state: StoryStateItem) => void;
  onOpenList: () => void;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white">
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-2.5">
        <div className="min-w-0">
          <p className="text-sm font-black text-slate-950">本章承接要求</p>
          <p className="mt-0.5 truncate text-xs text-slate-500">当前章节需要保持一致的状态项。</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Badge
            tone={items.length > 0 ? "amber" : "slate"}
            className="whitespace-nowrap rounded-md !px-1.5 !py-0.5 !text-[10px]"
          >
            {items.length} 条
          </Badge>
          <button
            type="button"
            className="inline-flex h-6 shrink-0 items-center gap-1 whitespace-nowrap rounded-md px-1.5 text-[10px] font-semibold text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
            onClick={onOpenList}
          >
            <Eye className="size-3" /> 本章全部
          </button>
        </div>
      </div>
      {items.length === 0 ? (
        <div className="px-4 py-6 text-sm text-slate-500">
          暂无承接要求，可点击“本章全部”确认列表状态。
        </div>
      ) : (
        <div className="max-h-72 divide-y divide-slate-100 overflow-y-auto">
          {items.map(({ requirement, state }) => (
            <div key={requirement.id} className="px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={getRequirementTone(requirement.requirement_type)}>
                      {REQUIREMENT_TYPE_LABEL[requirement.requirement_type] ??
                        requirement.requirement_type}
                    </Badge>
                    <Badge tone={getRequirementOriginTone(requirement)}>
                      {formatRequirementOriginLabel(requirement)}
                    </Badge>
                    {state?.is_hard_constraint ? (
                      <Badge tone="rose">硬约束</Badge>
                    ) : null}
                    {state && state.status !== "active" ? (
                      <Badge tone={getStoryStateStatusTone(state.status)}>
                        {STORY_STATE_STATUS_LABEL[state.status] ?? state.status}
                      </Badge>
                    ) : null}
                  </div>
                  <p className="mt-2 truncate text-sm font-bold text-slate-950">
                    {state?.name ?? "关联关键设定不可用"}
                  </p>
                </div>
                <span className="shrink-0 text-[11px] font-semibold text-slate-400">
                  P{requirement.priority}
                </span>
              </div>
              <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-600">
                {requirement.summary || state?.summary || "—"}
              </p>
              <div className="mt-2 flex items-center justify-between gap-2">
                <p className="min-w-0 truncate text-[11px] text-slate-400">
                  {state ? storyStateMeta(state) : `关联 ID：${requirement.state_item_id}`}
                </p>
                {state ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 shrink-0 px-2 text-[11px]"
                    onClick={() => onSelectState(state)}
                  >
                    <Eye className="size-3.5" /> 查看
                  </Button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StoryStatePanel({
  items,
  totalCount,
  onSelectState,
  onOpenList,
}: {
  items: StoryStateItem[];
  totalCount: number;
  onSelectState: (state: StoryStateItem) => void;
  onOpenList: () => void;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white">
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-2.5">
        <div className="min-w-0">
          <p className="text-sm font-black text-slate-950">关键设定</p>
          <p className="mt-0.5 truncate text-xs text-slate-500">当前项目已提取的活跃状态项。</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Badge
            tone={totalCount > 0 ? "blue" : "slate"}
            className="whitespace-nowrap rounded-md !px-1.5 !py-0.5 !text-[10px]"
          >
            {totalCount} 条
          </Badge>
          <button
            type="button"
            className="inline-flex h-6 shrink-0 items-center gap-1 whitespace-nowrap rounded-md px-1.5 text-[10px] font-semibold text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
            onClick={onOpenList}
          >
            <Eye className="size-3" /> 全部
          </button>
        </div>
      </div>
      {items.length === 0 ? (
        <div className="px-4 py-6 text-sm text-slate-500">
          暂无已提取的关键设定，可点击“全部”确认列表状态。
        </div>
      ) : (
        <div className="max-h-72 divide-y divide-slate-100 overflow-y-auto">
          {items.map((item) => (
            <div key={item.id} className="px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={getStoryStateTone(item)}>
                      {STORY_STATE_TYPE_LABEL[item.state_type] ?? item.state_type}
                    </Badge>
                    {item.is_hard_constraint ? <Badge tone="rose">硬约束</Badge> : null}
                  </div>
                  <p className="mt-2 truncate text-sm font-bold text-slate-950">
                    {item.name}
                  </p>
                </div>
                <span className="shrink-0 text-[11px] font-semibold text-slate-400">
                  P{item.priority}
                </span>
              </div>
              <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-600">
                {item.summary || "—"}
              </p>
              <div className="mt-2 flex items-center justify-between gap-2">
                <p className="min-w-0 truncate text-[11px] text-slate-400">
                  {storyStateMeta(item)}
                </p>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 shrink-0 px-2 text-[11px]"
                  onClick={() => onSelectState(item)}
                >
                  <Eye className="size-3.5" /> 查看
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function OutlinePage({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const projectKey = useScopedKey("project", projectId);
  const chaptersKey = useScopedKey("project", projectId, "chapters");
  const jobsKey = useScopedKey("jobs");

  const { data: chapterRows = [] } = useQuery({
    queryKey: chaptersKey,
    queryFn: () => chaptersApi.list(projectId),
  });
  const chapters = useMemo(
    () =>
      [...chapterRows].sort(
        (a, b) => (a.chapter_index ?? 0) - (b.chapter_index ?? 0),
      ),
    [chapterRows],
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
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<OutlineFilter>("all");
  const [quickView, setQuickView] = useState<OutlineQuickView>("all");
  const [jumpChapter, setJumpChapter] = useState("");
  const [sceneCountMode, setSceneCountMode] = useState<"auto" | "manual">("auto");
  const [manualSceneCount, setManualSceneCount] = useState(3);
  const [revisionConfig, setRevisionConfig] = useState<RevisionDrawerConfig | null>(null);
  const [selectedStoryState, setSelectedStoryState] = useState<StoryStateItem | null>(null);
  const [showChapterRequirementList, setShowChapterRequirementList] = useState(false);
  const [showStoryStateList, setShowStoryStateList] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const [highlightChapterId, setHighlightChapterId] = useState<string | null>(null);
  const [batchScenePlanJobId, setBatchScenePlanJobId] = useState<string | null>(null);
  const chapterItemRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const previousActiveIdRef = useRef<string | null>(null);
  const allScenesKey = useScopedKey("project", projectId, "scenes", "all");
  const { data: allScenes = [] } = useQuery({
    queryKey: allScenesKey,
    queryFn: () => scenesApi.list(projectId),
    enabled: chapters.length > 0,
  });
  const chapterSceneMeta = useMemo(() => {
    const sceneCountByChapter = new Map<string, number>();
    const writtenChapterIds = new Set<string>();

    allScenes.forEach((scene) => {
      sceneCountByChapter.set(
        scene.chapter_id,
        (sceneCountByChapter.get(scene.chapter_id) ?? 0) + 1,
      );
      if (WRITTEN_SCENE_STATUSES.has(scene.status)) {
        writtenChapterIds.add(scene.chapter_id);
      }
    });

    return { sceneCountByChapter, writtenChapterIds };
  }, [allScenes]);
  const filterMatchesChapter = useCallback(
    (chapter: Chapter, filter: OutlineFilter) => {
      const sceneCount = chapterSceneMeta.sceneCountByChapter.get(chapter.id) ?? 0;
      const hasScenes = sceneCount > 0;
      const isWritten = chapterSceneMeta.writtenChapterIds.has(chapter.id);

      switch (filter) {
        case "no-scenes":
          return !hasScenes;
        case "has-scenes":
          return hasScenes;
        case "written":
          return isWritten;
        case "safe-optimize":
          return !hasScenes;
        case "all":
        default:
          return true;
      }
    },
    [chapterSceneMeta],
  );
  const filteredChapters = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase();
    return chapters.filter((chapter) => {
      const matchesKeyword =
        !keyword ||
        (chapter.title?.toLowerCase() ?? "").includes(keyword) ||
        (chapter.summary?.toLowerCase() ?? "").includes(keyword);
      return matchesKeyword && filterMatchesChapter(chapter, statusFilter);
    });
  }, [chapters, filterMatchesChapter, searchTerm, statusFilter]);
  const activeGroupKey = useMemo(() => {
    if (!activeId) return null;
    const activeChapter = chapters.find((chapter) => chapter.id === activeId);
    if (!activeChapter) return null;
    const chapterIndex = activeChapter.chapter_index || 1;
    const start =
      Math.floor(Math.max(chapterIndex - 1, 0) / CHAPTER_GROUP_SIZE) * CHAPTER_GROUP_SIZE + 1;
    return `${start}-${start + CHAPTER_GROUP_SIZE - 1}`;
  }, [activeId, chapters]);
  const scopedChapters = useMemo(() => {
    if (quickView !== "current-group" || !activeGroupKey) {
      return filteredChapters;
    }
    return filteredChapters.filter((chapter) => {
      const chapterIndex = chapter.chapter_index || 1;
      const start =
        Math.floor(Math.max(chapterIndex - 1, 0) / CHAPTER_GROUP_SIZE) * CHAPTER_GROUP_SIZE + 1;
      return `${start}-${start + CHAPTER_GROUP_SIZE - 1}` === activeGroupKey;
    });
  }, [activeGroupKey, filteredChapters, quickView]);
  const chapterGroups = useMemo(() => {
    const groups = new Map<
      string,
      { key: string; label: string; start: number; end: number; chapters: Chapter[] }
    >();

    scopedChapters.forEach((chapter) => {
      const chapterIndex = chapter.chapter_index || 1;
      const start =
        Math.floor(Math.max(chapterIndex - 1, 0) / CHAPTER_GROUP_SIZE) * CHAPTER_GROUP_SIZE + 1;
      const end = start + CHAPTER_GROUP_SIZE - 1;
      const key = `${start}-${end}`;
      const existing = groups.get(key);

      if (existing) {
        existing.chapters.push(chapter);
        return;
      }

      groups.set(key, {
        key,
        label: `${start}-${end} 章`,
        start,
        end,
        chapters: [chapter],
      });
    });

    return Array.from(groups.values()).sort((a, b) => a.start - b.start);
  }, [scopedChapters]);
  const filterOptions = useMemo(
    () => [
      { key: "all" as const, label: "全部", count: chapters.length },
      {
        key: "no-scenes" as const,
        label: "未生成场景",
        count: chapters.filter((chapter) => filterMatchesChapter(chapter, "no-scenes")).length,
      },
      {
        key: "has-scenes" as const,
        label: "已有场景",
        count: chapters.filter((chapter) => filterMatchesChapter(chapter, "has-scenes")).length,
      },
      {
        key: "written" as const,
        label: "已写正文",
        count: chapters.filter((chapter) => filterMatchesChapter(chapter, "written")).length,
      },
      {
        key: "safe-optimize" as const,
        label: "可安全优化",
        count: chapters.filter((chapter) => filterMatchesChapter(chapter, "safe-optimize")).length,
      },
    ],
    [chapters, filterMatchesChapter],
  );
  const quickViewOptions = useMemo(
    () => [
      { key: "all" as const, label: "全部目录" },
      { key: "current-group" as const, label: "当前分组" },
      { key: "safe-optimize" as const, label: "可优化优先" },
      { key: "written" as const, label: "已写正文" },
    ],
    [],
  );
  const active = useMemo(() => {
    if (activeId) {
      const matched = chapters.find((chapter) => chapter.id === activeId);
      if (matched && filteredChapters.some((chapter) => chapter.id === matched.id)) {
        return matched;
      }
    }
    return filteredChapters[0] ?? chapters[0];
  }, [activeId, chapters, filteredChapters]);
  const activeIndex = active
    ? chapters.findIndex((chapter) => chapter.id === active.id)
    : -1;
  const previousChapter = activeIndex > 0 ? chapters[activeIndex - 1] : null;
  const nextChapter =
    activeIndex >= 0 && activeIndex < chapters.length - 1 ? chapters[activeIndex + 1] : null;

  useEffect(() => {
    if (!activeId && filteredChapters[0]) {
      // CI(react-hooks/set-state-in-effect): 初始化"默认选中首章"的同步行为，
      // 仅在 activeId 缺失时触发一次，不会引发级联渲染。
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setActiveId(filteredChapters[0].id);
    }
  }, [activeId, filteredChapters]);

  useEffect(() => {
    if (!active && filteredChapters[0]) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setActiveId(filteredChapters[0].id);
      return;
    }
    if (!activeId || !active) return;
    if (!filteredChapters.some((chapter) => chapter.id === activeId) && filteredChapters[0]) {
      setActiveId(filteredChapters[0].id);
    }
  }, [active, activeId, filteredChapters]);

  useEffect(() => {
    if (!active?.id) return;

    const frame = window.requestAnimationFrame(() => {
      chapterItemRefs.current[active.id]?.scrollIntoView({
        block: highlightChapterId === active.id ? "center" : "nearest",
        behavior: "smooth",
      });
    });

    return () => window.cancelAnimationFrame(frame);
  }, [active?.id, chapterGroups, collapsedGroups, highlightChapterId]);

  useEffect(() => {
    const previousActiveId = previousActiveIdRef.current;
    previousActiveIdRef.current = active?.id ?? null;

    if (!active || previousActiveId === active.id) return;

    const group = chapterGroups.find((item) =>
      item.chapters.some((chapter) => chapter.id === active.id),
    );
    if (!group || !collapsedGroups[group.key]) return;
    // active 切到 collapsed group 时自动展开该 group，UX 必要的副作用。
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCollapsedGroups((current) => ({ ...current, [group.key]: false }));
  }, [active, chapterGroups, collapsedGroups]);

  useEffect(() => {
    if (chapterGroups.length === 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setCollapsedGroups({});
      return;
    }

    setCollapsedGroups((current) => {
      const next: Record<string, boolean> = {};
      const currentGroupKey =
        chapterGroups.find((group) =>
          group.chapters.some((chapter) => chapter.id === active?.id),
        )?.key ?? null;

      chapterGroups.forEach((group) => {
        if (group.key in current) {
          next[group.key] = current[group.key];
          return;
        }
        next[group.key] = group.key !== currentGroupKey;
      });

      return next;
    });
  }, [active?.id, chapterGroups]);

  useEffect(() => {
    if (!highlightChapterId) return;
    const timer = window.setTimeout(() => {
      setHighlightChapterId((current) =>
        current === highlightChapterId ? null : current,
      );
    }, 2200);
    return () => window.clearTimeout(timer);
  }, [highlightChapterId]);

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
  const storyStatesKey = useScopedKey("project", projectId, "story-states", "active");
  const activeRequirementsKey = useScopedKey(
    "project",
    projectId,
    "chapters",
    active?.id,
    "state-requirements",
  );
  const { data: storyStateResponse } = useQuery({
    queryKey: storyStatesKey,
    queryFn: () => storyStatesApi.list(projectId, { status: "active", limit: 80 }),
    enabled: chapters.length > 0,
  });
  const { data: requirementResponse } = useQuery({
    queryKey: activeRequirementsKey,
    queryFn: () =>
      active
        ? storyStatesApi.listChapterRequirements(projectId, active.id)
        : Promise.resolve({ items: [] }),
    enabled: !!active,
  });
  const storyStates = useMemo(
    () => storyStateResponse?.items ?? [],
    [storyStateResponse],
  );
  const chapterRequirements = useMemo(
    () => requirementResponse?.items ?? [],
    [requirementResponse],
  );
  const storyStateById = useMemo(
    () => new Map(storyStates.map((item) => [item.id, item])),
    [storyStates],
  );
  const activeRequirementItems = useMemo(
    () =>
      chapterRequirements
        .map((requirement) => ({
          requirement,
          state:
            requirement.state_item ??
            storyStateById.get(requirement.state_item_id) ??
            null,
        }))
        .sort((a, b) => b.requirement.priority - a.requirement.priority),
    [chapterRequirements, storyStateById],
  );
  const storyStateHighlights = useMemo(
    () => storyStates.slice(0, 8),
    [storyStates],
  );
  const activeSceneStats = useMemo(() => {
    if (!active) {
      return { count: 0, isSafeToOptimize: false, hasWrittenScene: false };
    }
    const count = chapterSceneMeta.sceneCountByChapter.get(active.id) ?? scenes.length;
    return {
      count,
      isSafeToOptimize: count === 0,
      hasWrittenScene: chapterSceneMeta.writtenChapterIds.has(active.id),
    };
  }, [active, chapterSceneMeta, scenes.length]);

  const invalidateRevisionTargets = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: chaptersKey });
    queryClient.invalidateQueries({ queryKey: scenesKey });
    queryClient.invalidateQueries({ queryKey: allScenesKey });
    queryClient.invalidateQueries({ queryKey: storyStatesKey });
    queryClient.invalidateQueries({ queryKey: activeRequirementsKey });
    queryClient.invalidateQueries({ queryKey: jobsKey });
    queryClient.invalidateQueries({ queryKey: projectKey });
  }, [
    queryClient,
    chaptersKey,
    scenesKey,
    allScenesKey,
    storyStatesKey,
    activeRequirementsKey,
    jobsKey,
    projectKey,
  ]);

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
          queryClient.invalidateQueries({ queryKey: allScenesKey });
          queryClient.invalidateQueries({ queryKey: activeRequirementsKey });
        } else if (jobType === "write_scene" || jobType === "rewrite_scene") {
          queryClient.invalidateQueries({ queryKey: scenesKey });
          queryClient.invalidateQueries({ queryKey: allScenesKey });
          queryClient.invalidateQueries({ queryKey: storyStatesKey });
          queryClient.invalidateQueries({ queryKey: activeRequirementsKey });
        }
      }
    },
    [
      queryClient,
      jobsKey,
      chaptersKey,
      projectKey,
      scenesKey,
      allScenesKey,
      storyStatesKey,
      activeRequirementsKey,
    ],
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
      queryClient.invalidateQueries({ queryKey: allScenesKey });
      queryClient.invalidateQueries({ queryKey: activeRequirementsKey });
      queryClient.invalidateQueries({ queryKey: jobsKey });
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "提交失败");
    },
  });

  const batchGenerateScenes = useMutation({
    mutationFn: () =>
      batchApi.generateAllScenes(projectId, {
        scenes_per_chapter: sceneCountMode === "manual" ? manualSceneCount : null,
        expected_words: 1500,
        force_regenerate: false,
      }),
    onSuccess: (job) => {
      toast.success("已启动批量场景规划");
      setBatchScenePlanJobId(job.id);
      queryClient.invalidateQueries({ queryKey: jobsKey });
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "提交失败");
    },
  });

  const batchPolish = useMutation({
    mutationFn: () => batchApi.polishAllChapters(projectId, { force: false }),
    onSuccess: (job) => {
      toast.success("已启动批量章后润色");
      setBatchScenePlanJobId(job.id);
      queryClient.invalidateQueries({ queryKey: jobsKey });
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "提交失败");
    },
  });

  const jumpToChapter = useCallback(() => {
    const target = Number(jumpChapter);
    if (!Number.isInteger(target) || target <= 0) {
      toast.error("请输入有效章节号");
      return;
    }
    const matched = chapters.find((chapter) => chapter.chapter_index === target);
    if (!matched) {
      toast.error(`未找到第 ${target} 章`);
      return;
    }
    setActiveId(matched.id);
    setHighlightChapterId(matched.id);
    setQuickView("all");
  }, [chapters, jumpChapter]);

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
                variant="secondary"
                onClick={() => batchGenerateScenes.mutate()}
                disabled={batchGenerateScenes.isPending || chapters.length === 0}
              >
                {batchGenerateScenes.isPending ? (
                  <RefreshCw className="size-4 animate-spin" />
                ) : (
                  <Wand2 className="size-4" />
                )}
                批量生成所有场景
              </Button>
              <Button
                variant="secondary"
                onClick={() => batchPolish.mutate()}
                disabled={batchPolish.isPending || chapters.length === 0}
              >
                {batchPolish.isPending ? (
                  <RefreshCw className="size-4 animate-spin" />
                ) : (
                  <Sparkles className="size-4" />
                )}
                批量章后润色
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
          <CardHeader className="border-b border-slate-100 pb-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <CardTitle>章节大纲树</CardTitle>
                <p className="mt-1 text-sm text-slate-500">像目录一样快速定位章节与切换处理对象。</p>
              </div>
              <Badge tone="blue">{chapters.length} 章</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5 rounded-2xl border border-slate-200 bg-slate-50/45 p-1.5">
              <label className="relative block">
                <Search className="absolute left-2.5 top-2.5 size-3 text-slate-400" />
                <input
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                  placeholder="搜索章节标题或摘要"
                  className="h-7.5 w-full rounded-lg border border-slate-200 bg-white py-1 pl-8 pr-2.5 text-xs outline-none focus:border-indigo-500"
                />
              </label>
              <div className="flex items-center gap-1">
                <span className="shrink-0 text-[11px] font-semibold text-slate-500">跳到章节</span>
                <input
                  value={jumpChapter}
                  onChange={(event) => setJumpChapter(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") jumpToChapter();
                  }}
                  inputMode="numeric"
                  placeholder="输入章节号"
                  className="h-7.5 min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-2.5 text-xs outline-none focus:border-indigo-500"
                />
                <Button
                  variant="secondary"
                  className="h-7 rounded-lg px-2 text-[10px] font-medium text-slate-600"
                  onClick={jumpToChapter}
                >
                  跳转
                </Button>
              </div>
              <div className="space-y-1 rounded-lg border border-slate-200 bg-white/85 p-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] font-semibold uppercase tracking-[0.15em] text-slate-400">
                    按进度筛选
                  </span>
                  <span className="text-[9px] text-slate-400">快速定位</span>
                </div>
                <div className="grid grid-cols-2 gap-1">
                  {filterOptions.map((option) => (
                    <button
                      key={option.key}
                      type="button"
                      onClick={() => setStatusFilter(option.key)}
                      className={`inline-flex min-h-7 items-center justify-between rounded-full border px-2 py-0.5 text-[10px] font-semibold transition ${
                        statusFilter === option.key
                          ? "border-indigo-200 bg-indigo-50 text-indigo-700"
                          : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900"
                      }`}
                    >
                      <span className="truncate">{option.label}</span>
                      <span className="ml-1 shrink-0 text-[9px] text-slate-400">{option.count}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div className="space-y-1 rounded-lg border border-slate-200 bg-white/85 p-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] font-semibold uppercase tracking-[0.15em] text-slate-400">
                    快捷视图
                  </span>
                  <span className="text-[9px] text-slate-400">当前范围</span>
                </div>
                <div className="grid grid-cols-2 gap-1">
                  {quickViewOptions.map((option) => (
                    <button
                      key={option.key}
                      type="button"
                      onClick={() => {
                        setQuickView(option.key);
                        if (option.key === "safe-optimize") {
                          setStatusFilter("safe-optimize");
                        } else if (option.key === "written") {
                          setStatusFilter("written");
                        } else if (
                          statusFilter === "safe-optimize" ||
                          statusFilter === "written"
                        ) {
                          setStatusFilter("all");
                        }
                      }}
                      className={`inline-flex min-h-7 items-center justify-center rounded-full border px-2 py-0.5 text-[10px] font-semibold transition ${
                        quickView === option.key
                          ? "border-slate-900 bg-slate-900 text-white"
                          : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900"
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white px-3 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
                <span>显示 {scopedChapters.length} / {chapters.length} 章</span>
                <span>{chapterGroups.length > 0 ? `${chapterGroups.length} 个分组` : "0 个分组"}</span>
                {active ? <span>当前：第 {active.chapter_index} 章</span> : null}
              </div>
            </div>
            {chapters.length === 0 ? (
              <p className="py-8 text-center text-sm text-slate-500">尚未生成章节大纲。</p>
            ) : filteredChapters.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-10 text-center">
                <p className="text-sm font-semibold text-slate-700">没有匹配的章节</p>
                <p className="mt-1 text-xs text-slate-500">换一个标题关键词，或直接输入章节号跳转。</p>
              </div>
            ) : (
              <div className="max-h-[70vh] space-y-2 overflow-y-auto rounded-2xl border border-slate-100 bg-slate-50/40 p-2 pr-1">
                {chapterGroups.map((group) => {
                  const isCollapsed = collapsedGroups[group.key] ?? false;
                  return (
                    <div key={group.key} className="rounded-2xl border border-slate-200 bg-white/90 p-2">
                      <button
                        type="button"
                        onClick={() =>
                          setCollapsedGroups((current) => ({
                            ...current,
                            [group.key]: !isCollapsed,
                          }))
                        }
                        className="sticky top-0 z-10 flex w-full items-center justify-between gap-3 rounded-xl border border-transparent bg-white/95 px-2 py-2 text-left backdrop-blur hover:bg-slate-50"
                      >
                        <div>
                          <p className="text-sm font-bold text-slate-900">{group.label}</p>
                          <p className="text-xs text-slate-500">
                            {group.chapters.length} 章 · 第 {group.start} 章到第{" "}
                            {Math.min(group.end, chapters[chapters.length - 1]?.chapter_index ?? group.end)} 章
                          </p>
                        </div>
                        <div className="flex items-center gap-2 text-slate-500">
                          <Badge tone="slate">{group.chapters.length}</Badge>
                          {isCollapsed ? (
                            <ChevronDown className="size-4" />
                          ) : (
                            <ChevronUp className="size-4" />
                          )}
                        </div>
                      </button>
                      {!isCollapsed ? (
                        <div className="mt-2 space-y-2">
                          {group.chapters.map((chapter) => {
                            const sceneCount =
                              chapterSceneMeta.sceneCountByChapter.get(chapter.id) ?? 0;
                            const isWritten = chapterSceneMeta.writtenChapterIds.has(chapter.id);

                            return (
                              <button
                                key={chapter.id}
                                ref={(node) => {
                                  chapterItemRefs.current[chapter.id] = node;
                                }}
                                type="button"
                                onClick={() => setActiveId(chapter.id)}
                                className={`w-full rounded-2xl border px-4 py-3 text-left transition ${
                                  active?.id === chapter.id && highlightChapterId === chapter.id
                                    ? "border-indigo-300 bg-gradient-to-r from-amber-50 to-indigo-50 shadow-sm shadow-amber-100 ring-2 ring-amber-200"
                                    : highlightChapterId === chapter.id
                                      ? "border-amber-300 bg-amber-50 shadow-sm shadow-amber-100 ring-2 ring-amber-200"
                                      : active?.id === chapter.id
                                        ? "border-indigo-300 bg-indigo-50 shadow-sm shadow-indigo-100 ring-1 ring-indigo-100"
                                        : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                                }`}
                              >
                                <div className="flex items-start justify-between gap-3">
                                  <div className="min-w-0">
                                    <div className="flex items-center gap-2">
                                      <span
                                        className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${
                                          active?.id === chapter.id
                                            ? "bg-indigo-600 text-white"
                                            : "bg-slate-100 text-slate-600"
                                        }`}
                                      >
                                        #{chapter.chapter_index}
                                      </span>
                                      <p className="truncate text-sm font-bold text-slate-950">
                                        {chapter.title}
                                      </p>
                                    </div>
                                    <p className="mt-1 line-clamp-1 text-xs text-slate-500">
                                      {chapter.summary || "—"}
                                    </p>
                                    <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                                      <span className="rounded-full bg-slate-100 px-2 py-0.5">
                                        {sceneCount > 0 ? `${sceneCount} 个场景` : "未生成场景"}
                                      </span>
                                      {isWritten ? (
                                        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-700">
                                          已写正文
                                        </span>
                                      ) : null}
                                      {sceneCount === 0 ? (
                                        <span className="rounded-full bg-violet-50 px-2 py-0.5 text-violet-700">
                                          可安全优化
                                        </span>
                                      ) : null}
                                    </div>
                                  </div>
                                  <StatusBadge status={chapter.status as never} />
                                </div>
                              </button>
                            );
                          })}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
        {active ? (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>当前章节大纲</CardTitle>
                <p className="mt-1 text-xs text-slate-500">
                  第 {active.chapter_index} 章 / 共 {chapters.length} 章
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => previousChapter && setActiveId(previousChapter.id)}
                  disabled={!previousChapter}
                >
                  <ChevronLeft className="size-3.5" /> 上一章
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => nextChapter && setActiveId(nextChapter.id)}
                  disabled={!nextChapter}
                >
                  下一章 <ChevronRight className="size-3.5" />
                </Button>
                <Badge tone={activeSceneStats.isSafeToOptimize ? "violet" : "amber"}>
                  {activeSceneStats.isSafeToOptimize
                    ? "可安全优化"
                    : `已有 ${activeSceneStats.count} 个场景，自动应用会受限`}
                </Badge>
                {activeSceneStats.hasWrittenScene ? <Badge tone="green">已写正文</Badge> : null}
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
              <div className="grid gap-3 lg:grid-cols-2">
                <ChapterRequirementPanel
                  items={activeRequirementItems}
                  onSelectState={setSelectedStoryState}
                  onOpenList={() => setShowChapterRequirementList(true)}
                />
                <StoryStatePanel
                  items={storyStateHighlights}
                  totalCount={storyStates.length}
                  onSelectState={setSelectedStoryState}
                  onOpenList={() => setShowStoryStateList(true)}
                />
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
                    key: "budget",
                    header: "预算",
                    render: (row) => (
                      <div className="min-w-[150px] space-y-1">
                        <p className="text-sm font-semibold text-slate-800">
                          {row.target_words ? `约 ${row.target_words} 字` : "—"}
                        </p>
                        {row.beat_group_summary ? (
                          <p className="line-clamp-2 text-xs leading-relaxed text-slate-500">
                            {row.beat_group_summary}
                          </p>
                        ) : row.beat_start || row.beat_end ? (
                          <p className="text-xs text-slate-500">
                            beat {row.beat_start ?? "?"}-{row.beat_end ?? "?"}
                          </p>
                        ) : null}
                      </div>
                    ),
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
                      <option value="auto">按章节节奏自动</option>
                      {[1, 2, 3, 4, 5, 6, 7, 8].map((count) => (
                        <option key={count} value={count}>
                          {count} 个
                        </option>
                      ))}
                    </select>
                    <span className="ml-2 text-[11px] font-medium text-slate-400">
                      按字数、节奏和拍点合并
                    </span>
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
      {batchScenePlanJobId ? (
        <BatchJobProgressDialog
          projectId={projectId}
          batchJobId={batchScenePlanJobId}
          onComplete={() => {
            queryClient.invalidateQueries({ queryKey: allScenesKey });
            queryClient.invalidateQueries({ queryKey: scenesKey });
            queryClient.invalidateQueries({ queryKey: jobsKey });
          }}
          onClose={() => setBatchScenePlanJobId(null)}
        />
      ) : null}
      {showChapterRequirementList && active ? (
        <ChapterRequirementListDialog
          projectId={projectId}
          chapterId={active.id}
          chapterLabel={`第 ${active.chapter_index} 章`}
          items={activeRequirementItems}
          stateOptions={storyStates}
          onClose={() => setShowChapterRequirementList(false)}
          onSelectState={(state) => {
            setShowChapterRequirementList(false);
            setSelectedStoryState(state);
          }}
          onChanged={() => {
            queryClient.invalidateQueries({ queryKey: activeRequirementsKey });
            queryClient.invalidateQueries({ queryKey: storyStatesKey });
          }}
        />
      ) : null}
      {showStoryStateList ? (
        <StoryStateListDialog
          items={storyStates}
          onClose={() => setShowStoryStateList(false)}
          onSelectState={(state) => {
            setShowStoryStateList(false);
            setSelectedStoryState(state);
          }}
        />
      ) : null}
      {selectedStoryState ? (
        <StoryStateDetailDialog
          projectId={projectId}
          state={selectedStoryState}
          onClose={() => setSelectedStoryState(null)}
          onSaved={() => {
            queryClient.invalidateQueries({ queryKey: storyStatesKey });
            queryClient.invalidateQueries({ queryKey: activeRequirementsKey });
          }}
        />
      ) : null}
    </div>
  );
}
