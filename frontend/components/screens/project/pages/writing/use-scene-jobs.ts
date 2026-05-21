"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { jobsApi, type GenerationJob, type Scene } from "@/lib/api";
import { useProjectEvents, type ProjectEvent } from "@/lib/hooks/use-event-source";
import { useScopedKey } from "@/lib/use-scoped-key";

export type UseSceneJobsArgs = {
  projectId: string;
  activeScene?: Scene;
};

/**
 * 写作工作台：jobs 列表查询 + 当前 scene 三类任务（write/audit/rewrite）的派生状态。
 *
 * SSE 接管实时状态变化：``useProjectEvents`` 监听 ``project:{id}`` channel，
 * 收到 ``job.*`` 事件后立即 ``invalidateQueries(jobsKey)``，把"任务状态
 * 从后端到 UI"的延迟从 1500ms 降到 < 200ms。
 *
 * 兜底：``refetchInterval`` 改为 30s，覆盖 SSE 断开 / 错过事件场景。
 */
export function useSceneJobs({ projectId, activeScene }: UseSceneJobsArgs) {
  const queryClient = useQueryClient();
  const jobsKey = useScopedKey("jobs");

  const { data: jobs = [] } = useQuery({
    queryKey: jobsKey,
    queryFn: () => jobsApi.list(),
    refetchInterval: (query) => {
      const list = (query.state.data as GenerationJob[] | undefined) ?? [];
      const active = list.find(
        (j) =>
          j.project_id === projectId &&
          ["write_scene", "audit_scene", "rewrite_scene"].includes(j.job_type) &&
          (j.status === "queued" || j.status === "running"),
      );
      return active ? 30000 : false;
    },
  });

  const handleProjectEvent = useCallback(
    (event: ProjectEvent) => {
      if (event.type.startsWith("job.")) {
        queryClient.invalidateQueries({ queryKey: jobsKey });
      }
    },
    [queryClient, jobsKey],
  );
  useProjectEvents(projectId, { onMessage: handleProjectEvent });

  const latestSceneJob = jobs.find(
    (j) =>
      j.project_id === projectId &&
      j.job_type === "write_scene" &&
      (j.input_payload as { scene_id?: string } | null | undefined)?.scene_id ===
        activeScene?.id,
  );
  const isWriting =
    latestSceneJob?.status === "queued" || latestSceneJob?.status === "running";

  const latestAuditJob = jobs.find(
    (j) =>
      j.project_id === projectId &&
      j.job_type === "audit_scene" &&
      (j.input_payload as { scene_id?: string } | null | undefined)?.scene_id ===
        activeScene?.id,
  );
  const isAuditing =
    latestAuditJob?.status === "queued" || latestAuditJob?.status === "running";
  const latestAuditPayload = latestAuditJob?.output_payload as
    | { issue_count?: number }
    | null
    | undefined;
  const latestAuditIssueCount =
    typeof latestAuditPayload?.issue_count === "number"
      ? latestAuditPayload.issue_count
      : undefined;

  const latestRewriteJob = jobs.find(
    (j) =>
      j.project_id === projectId &&
      j.job_type === "rewrite_scene" &&
      (j.input_payload as { scene_id?: string } | null | undefined)?.scene_id ===
        activeScene?.id,
  );
  const isRewriting =
    latestRewriteJob?.status === "queued" || latestRewriteJob?.status === "running";

  return {
    jobsKey,
    jobs,
    latestSceneJob,
    isWriting,
    latestAuditJob,
    isAuditing,
    latestAuditIssueCount,
    latestRewriteJob,
    isRewriting,
  };
}
