"use client";

import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

import {
  continuityIssuesApi,
  type GenerationJob,
  projectsApi,
  type Scene,
} from "@/lib/api";
import { ApiError } from "@/lib/http";
import { useScopedKey } from "@/lib/use-scoped-key";

export type UseAuditRewriteArgs = {
  projectId: string;
  activeScene?: Scene;
  // jobs / versions / scenes 的 key，audit/rewrite 完成时需要 invalidate
  jobsKey: QueryKey;
  versionsKey: QueryKey;
  scenesKey: QueryKey;
  // 来自 use-scene-jobs：用于监听 audit 完成并 toast / 滚动
  latestAuditJob?: GenerationJob;
  latestAuditIssueCount?: number;
  // rewrite 成功时需要重置 displayed 版本（让 page 切回最新）
  onRewriteSuccess?: () => void;
};

/**
 * 写作工作台：审稿 / 重写流程。
 *
 * 包含：
 * - continuity_issues 查询 + 按当前 scene 切分（open / 全部）
 * - audit / rewrite mutations
 * - audit 完成时的 toast + 自动滚动到问题面板的 useEffect
 *
 * 仅由本组件触发的 audit 任务才会弹 toast——避免页面初次加载时
 * ��历史已结束的 audit 任务也通知一遍。
 */
export function useAuditRewrite({
  projectId,
  activeScene,
  jobsKey,
  versionsKey,
  scenesKey,
  latestAuditJob,
  latestAuditIssueCount,
  onRewriteSuccess,
}: UseAuditRewriteArgs) {
  const queryClient = useQueryClient();
  const issuesKey = useScopedKey("project", projectId, "continuity-issues");

  const { data: allIssues = [] } = useQuery({
    queryKey: issuesKey,
    queryFn: () => continuityIssuesApi.list(projectId),
    enabled: !!projectId,
  });

  const openIssueCountByScene = allIssues.reduce<Record<string, number>>((acc, issue) => {
    if (issue.scene_id && issue.status === "open") {
      acc[issue.scene_id] = (acc[issue.scene_id] ?? 0) + 1;
    }
    return acc;
  }, {});
  const sceneIssues = allIssues.filter((i) => i.scene_id === activeScene?.id);
  const sceneOpenIssues = sceneIssues.filter((i) => i.status === "open");

  const issuePanelRef = useRef<HTMLDivElement | null>(null);
  // 仅给「本组件提交过」的 audit job 弹 toast。
  const activeAuditJobIds = useRef<Set<string>>(new Set());
  const notifiedAuditJobIds = useRef<Set<string>>(new Set());

  const audit = useMutation({
    mutationFn: () => {
      if (!activeScene) {
        return Promise.reject(new Error("no_active_scene"));
      }
      return projectsApi.auditScene(projectId, activeScene.id, {
        estimate_words: 500,
      });
    },
    onSuccess: (job) => {
      activeAuditJobIds.current.add(job.id);
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
        target_words: activeScene.target_words || 1200,
        estimate_words: 2000,
      });
    },
    onSuccess: () => {
      toast.success("已提交重写任务");
      queryClient.invalidateQueries({ queryKey: jobsKey });
      queryClient.invalidateQueries({ queryKey: issuesKey });
      queryClient.invalidateQueries({ queryKey: scenesKey });
      queryClient.invalidateQueries({ queryKey: versionsKey });
      onRewriteSuccess?.();
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "重写提交失败");
    },
  });

  useEffect(() => {
    if (!latestAuditJob) return;
    if (latestAuditJob.status === "queued" || latestAuditJob.status === "running") {
      activeAuditJobIds.current.add(latestAuditJob.id);
      return;
    }
    if (notifiedAuditJobIds.current.has(latestAuditJob.id)) return;

    const shouldNotify = activeAuditJobIds.current.has(latestAuditJob.id);
    notifiedAuditJobIds.current.add(latestAuditJob.id);
    if (!shouldNotify) return;

    if (latestAuditJob.status === "succeeded") {
      queryClient.invalidateQueries({ queryKey: issuesKey });
      const count =
        typeof latestAuditIssueCount === "number" ? latestAuditIssueCount : 0;
      toast.success(
        count > 0 ? `审稿完成：发现 ${count} 个问题` : "审稿完成：未发现问题",
      );
      window.setTimeout(() => {
        issuePanelRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      }, 150);
    } else if (latestAuditJob.status === "failed") {
      toast.error(
        latestAuditJob.error_message
          ? `审稿失败：${latestAuditJob.error_message}`
          : "审稿失败",
      );
    }
  }, [latestAuditIssueCount, latestAuditJob, issuesKey, queryClient]);

  return {
    issuesKey,
    sceneIssues,
    sceneOpenIssues,
    openIssueCountByScene,
    issuePanelRef,
    audit,
    rewrite,
  };
}
