"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Layers3,
  Pencil,
  Plus,
  RefreshCw,
  Settings2,
  Sparkles,
  Wand2,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProjectHeader } from "@/components/screens/project/project-frame";
import { BibleBlock } from "@/components/screens/project/shared/bible-block";
import { PreflightCard } from "@/components/screens/project/shared/preflight-card";
import { taskTypeLabel } from "@/components/screens/project/shared/task-type-label";
import {
  type Bible,
  type BibleCharacter,
  type BiblePlotThread,
  type BibleWorldItem,
  type GenerateBiblePayload,
  type RevisionTargetType,
  characterRevisionsApi,
  plotThreadRevisionsApi,
  projectsApi,
  worldItemRevisionsApi,
} from "@/lib/api";
import { useProjectEvents, type ProjectEvent } from "@/lib/hooks/use-event-source";
import { ApiError } from "@/lib/http";
import { isPlatformAdmin } from "@/lib/permissions";
import { useScopedKey } from "@/lib/use-scoped-key";

import { BibleItem } from "./bible-item";
import { CharacterEditDialog } from "./character-edit-dialog";
import { type CreativePrefs, DEFAULT_PREFS, splitTags } from "./creative-prefs";
import { CreativePrefsCard } from "./creative-prefs-card";
import { DirectionPreviewDialog } from "./direction-preview-dialog";
import { EditableItem } from "./editable-item";
import { PlotThreadEditDialog } from "./plot-thread-edit-dialog";
import { ProjectStageCard } from "./project-stage-card";
import { RevisionCopilotDrawer } from "./revision-copilot-drawer";
import { SpecEditDialog } from "./spec-edit-dialog";
import { WillGenerateList } from "./will-generate-list";
import { WorldItemEditDialog } from "./world-item-edit-dialog";

type RevisionDrawerConfig = {
  scope: string;
  targetType?: RevisionTargetType | null;
  targetId?: string | null;
  title: string;
  description?: string;
  starterPrompts: string[];
};

const CORE_REVISION_CONFIG: RevisionDrawerConfig = {
  scope: "story_bible",
  targetType: "story_bible",
  title: "优化核心设定",
  description: "重点优化 Premise / Theme / Genre / Tone / POV / Style / continuity_rules，并检查跨模块影响。",
  starterPrompts: [
    "请优化核心设定，让 Premise、Theme、Tone、POV 和 Style Guide 更一致；如影响人物或大纲，请给出同组联动提案。",
    "请检查当前核心设定是否足以支撑长篇连载，补强 continuity_rules 和长期冲突约束。",
  ],
};

export function BiblePage({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isAdmin = isPlatformAdmin(user);
  const projectKey = useScopedKey("project", projectId);
  const bibleKey = useScopedKey("project", projectId, "bible");
  const charactersKey = useScopedKey("project", projectId, "characters");
  const worldItemsKey = useScopedKey("project", projectId, "world-items");
  const plotThreadsKey = useScopedKey("project", projectId, "plot-threads");
  const chaptersKey = useScopedKey("project", projectId, "chapters");
  const preflightKey = useScopedKey("project", projectId, "preflight", "generate_bible");
  const jobsKey = useScopedKey("jobs");
  const pendingCountsKey = useScopedKey(
    "project",
    projectId,
    "character-revisions-pending",
  );

  const { data: bible, isPending } = useQuery({
    queryKey: bibleKey,
    queryFn: () => projectsApi.getBible(projectId),
    refetchInterval: (query) => {
      // SSE 接管后只做 30s 兜底刷新：连接异常 / 中间错过事件时仍能收敛
      const data = query.state.data as Bible | undefined;
      const latestJob = data?.latest_job;
      const waitingForJob = latestJob?.status === "queued" || latestJob?.status === "running";
      const waitingForResult = latestJob?.status === "succeeded" && !data?.spec;
      return waitingForJob || waitingForResult ? 30000 : false;
    },
  });
  const { data: preflight } = useQuery({
    queryKey: preflightKey,
    queryFn: () => projectsApi.preflight(projectId, "generate_bible"),
  });
  // Sprint 10：人物卡显示"N 项待审核"badge（AI 推演产出的 pending revision 数）。
  // 每 6s 轻量轮询；任何应用/驳回操作会通过 onSaved invalidate 触发立即刷新。
  const { data: pendingCounts = [] } = useQuery({
    queryKey: pendingCountsKey,
    queryFn: () => characterRevisionsApi.pendingCount(projectId),
    refetchInterval: 6000,
  });
  const pendingByCharacter = new Map(
    pendingCounts.map((c) => [c.character_id, c.pending_count]),
  );
  // Sprint 12-C: 拉取 world / plot pending 角标。失败静默，不影响主流程。
  const worldPendingKey = useScopedKey("project", projectId, "world-item-pending");
  const plotPendingKey = useScopedKey("project", projectId, "plot-thread-pending");
  const { data: worldPending } = useQuery({
    queryKey: worldPendingKey,
    queryFn: () => worldItemRevisionsApi.pendingCount(projectId),
    refetchInterval: 30_000,
  });
  const { data: plotPending } = useQuery({
    queryKey: plotPendingKey,
    queryFn: () => plotThreadRevisionsApi.pendingCount(projectId),
    refetchInterval: 30_000,
  });
  const latestJob = bible?.latest_job;
  const isGenerating = latestJob?.status === "queued" || latestJob?.status === "running";

  // SSE：项目维度任务状态变化 → 立即失效相关 query（替代 1.5s 轮询）
  const handleProjectEvent = useCallback(
    (event: ProjectEvent) => {
      if (event.type.startsWith("job.")) {
        queryClient.invalidateQueries({ queryKey: bibleKey });
        queryClient.invalidateQueries({ queryKey: projectKey });
        queryClient.invalidateQueries({ queryKey: charactersKey });
        queryClient.invalidateQueries({ queryKey: worldItemsKey });
        queryClient.invalidateQueries({ queryKey: plotThreadsKey });
        queryClient.invalidateQueries({ queryKey: preflightKey });
        queryClient.invalidateQueries({ queryKey: jobsKey });
      } else if (event.type === "character_revision.created") {
        queryClient.invalidateQueries({ queryKey: charactersKey });
      }
    },
    [
      queryClient,
      bibleKey,
      projectKey,
      charactersKey,
      worldItemsKey,
      plotThreadsKey,
      preflightKey,
      jobsKey,
    ],
  );
  useProjectEvents(projectId, { onMessage: handleProjectEvent });

  const [prefsOpen, setPrefsOpen] = useState(false);
  const [prefsAdvanced, setPrefsAdvanced] = useState(false);
  const [defaultsExplain, setDefaultsExplain] = useState(false);
  const [prefs, setPrefs] = useState<CreativePrefs>(DEFAULT_PREFS);
  const [directionPreviewOpen, setDirectionPreviewOpen] = useState(false);
  const [specEditing, setSpecEditing] = useState(false);
  const [revisionConfig, setRevisionConfig] = useState<RevisionDrawerConfig | null>(null);
  const [editChar, setEditChar] = useState<BibleCharacter | "new" | null>(null);
  const [editWorld, setEditWorld] = useState<BibleWorldItem | "new" | null>(null);
  const [editThread, setEditThread] = useState<BiblePlotThread | "new" | null>(null);

  const generate = useMutation({
    mutationFn: () => {
      const payload: GenerateBiblePayload = {
        estimate_words: preflight?.estimate_words ?? 2000,
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

  const regenerateOutline = useMutation({
    mutationFn: () =>
      projectsApi.generateOutline(projectId, {
        target_chapters: preflight?.target_chapter_count || undefined,
        estimate_words: 3000,
        force_regenerate: true,
      }),
    onSuccess: () => {
      toast.success("已提交章节大纲重生成任务，故事圣经会保持不变");
      queryClient.invalidateQueries({ queryKey: chaptersKey });
      queryClient.invalidateQueries({ queryKey: projectKey });
      queryClient.invalidateQueries({ queryKey: jobsKey });
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "提交失败");
    },
  });

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: projectKey });
    queryClient.invalidateQueries({ queryKey: bibleKey });
    queryClient.invalidateQueries({ queryKey: charactersKey });
    queryClient.invalidateQueries({ queryKey: worldItemsKey });
    queryClient.invalidateQueries({ queryKey: plotThreadsKey });
    queryClient.invalidateQueries({ queryKey: chaptersKey });
    queryClient.invalidateQueries({ queryKey: pendingCountsKey });
    queryClient.invalidateQueries({ queryKey: worldPendingKey });
    queryClient.invalidateQueries({ queryKey: plotPendingKey });
  };

  const spec = bible?.spec;
  const characters = bible?.characters ?? [];
  const worldItems = bible?.world_items ?? [];
  const plotThreads = bible?.plot_threads ?? [];

  const canGenerate = preflight?.can_generate !== false;
  const disableGenerate = generate.isPending || isGenerating || !canGenerate;
  const disableOutlineRegenerate = regenerateOutline.isPending || !spec;
  const latestJobStatusText =
    latestJob?.status === "failed"
      ? `失败：${latestJob.error_message || "模型调用失败"}`
      : latestJob?.status === "succeeded"
        ? "已完成"
        : latestJob?.status ?? "—";

  const submitBibleGeneration = () => {
    if (
      spec &&
      !window.confirm(
        "这会重做故事圣经，并清空旧大纲/场景/正文。若你只想修章节，请点「只重生成大纲」。确定继续吗？",
      )
    ) {
      return;
    }
    generate.mutate();
  };

  const submitOutlineRegeneration = () => {
    if (
      !window.confirm(
        "这会保留当前故事圣经，只清空并重做章节大纲、场景和正文。确定继续吗？",
      )
    ) {
      return;
    }
    regenerateOutline.mutate();
  };

  const startAiOptimization = (config: RevisionDrawerConfig = CORE_REVISION_CONFIG) => {
    setRevisionConfig(config);
  };

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
              {spec ? (
                <Button variant="secondary" onClick={() => startAiOptimization()}>
                  <Sparkles className="size-4" /> AI 优化设定
                </Button>
              ) : null}
              {spec ? (
                <Button
                  variant="secondary"
                  onClick={submitOutlineRegeneration}
                  disabled={disableOutlineRegenerate}
                >
                  {regenerateOutline.isPending ? (
                    <RefreshCw className="size-4 animate-spin" />
                  ) : (
                    <Layers3 className="size-4" />
                  )}
                  只重生成大纲
                </Button>
              ) : null}
              <Button onClick={submitBibleGeneration} disabled={disableGenerate}>
                {isGenerating ? <RefreshCw className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                {spec ? "重做故事圣经" : "启动生成"}
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
                text={latestJobStatusText}
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
                <Button size="sm" variant="secondary" onClick={() => startAiOptimization()}>
                  <Sparkles className="size-3.5" /> AI 优化
                </Button>
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
                {[...(spec.constraints ?? []), ...(spec.continuity_rules ?? [])].map((item) => (
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
                  characters.map((character: BibleCharacter) => {
                    const pendingCount = pendingByCharacter.get(character.id) ?? 0;
                    return (
                      <EditableItem
                        key={character.id}
                        title={character.name}
                        badge={character.role}
                        text={[
                          character.description && `描述：${character.description}`,
                          character.personality && `性格：${character.personality}`,
                          character.motivation && `动机：${character.motivation}`,
                          character.secret && `秘密：${character.secret}`,
                          character.arc && `弧光：${character.arc}`,
                        ]
                          .filter(Boolean)
                          .join("\n")}
                        extraBadge={
                          pendingCount > 0 ? (
                            <Badge tone="amber">{pendingCount} 项待审核</Badge>
                          ) : undefined
                        }
                        onOptimize={() =>
                          startAiOptimization({
                            scope: "character",
                            targetType: "character",
                            targetId: character.id,
                            title: `优化人物：${character.name}`,
                            description: "重点优化人物动机、秘密、性格、弧光、关系和当前状态，并检查对剧情线/大纲的影响。",
                            starterPrompts: [
                              "请优化这个人物的动机、秘密、性格和弧光；如影响关系、剧情线或章节大纲，请给出同组联动提案。",
                              "请检查这个人物是否能支撑长篇成长线，补强 current_state 和 relationships 的可推进信息。",
                            ],
                          })
                        }
                        onEdit={() => setEditChar(character)}
                      />
                    );
                  })
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
                  plotThreads.map((thread: BiblePlotThread) => {
                    const pending = plotPending?.by_item?.[thread.id] ?? 0;
                    return (
                      <EditableItem
                        key={thread.id}
                        title={thread.title}
                        badge={`${thread.thread_type} · ${thread.status}`}
                        extraBadge={
                          pending > 0 ? (
                            <Badge tone="violet">{pending} 项待审核</Badge>
                          ) : null
                        }
                        text={thread.description}
                        onOptimize={() =>
                          startAiOptimization({
                            scope: "plot_thread",
                            targetType: "plot_thread",
                            targetId: thread.id,
                            title: `优化剧情线：${thread.title}`,
                            description: "重点优化主线/副线/伏笔/冲突推进，并检查人物、世界观和大纲联动。",
                            starterPrompts: [
                              "请优化这条剧情线的冲突推进、伏笔和阶段目标；如影响人物或章节大纲，请给出同组联动提案。",
                              "请检查这条剧情线是否有足够的中长期推进力，并补强关键转折和回收路径。",
                            ],
                          })
                        }
                        onEdit={() => setEditThread(thread)}
                      />
                    );
                  })
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
                worldItems.map((item: BibleWorldItem) => {
                  const pending = worldPending?.by_item?.[item.id] ?? 0;
                  return (
                    <EditableItem
                      key={item.id}
                      title={item.name}
                      badge={item.is_hard_rule ? "硬规则" : item.importance}
                      extraBadge={
                        pending > 0 ? (
                          <Badge tone="violet">{pending} 项待审核</Badge>
                        ) : null
                      }
                      text={item.description}
                      onOptimize={() =>
                        startAiOptimization({
                          scope: "world_item",
                          targetType: "world_item",
                          targetId: item.id,
                          title: `优化世界观：${item.name}`,
                          description: "重点优化地点、势力、硬规则、资源体系，并检查人物/剧情线/大纲联动。",
                          starterPrompts: [
                            "请优化这个世界观条目的规则、边界和长篇可持续性；如影响人物或剧情线，请给出同组联动提案。",
                            "请检查这个设定是否存在漏洞或与核心设定冲突，并给出可应用的修正方案。",
                          ],
                        })
                      }
                      onEdit={() => setEditWorld(item)}
                    />
                  );
                })
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
          onApplied={invalidateAll}
        />
      ) : null}
    </div>
  );
}
