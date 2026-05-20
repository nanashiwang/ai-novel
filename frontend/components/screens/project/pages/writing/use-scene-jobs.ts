"use client";

import { useQuery } from "@tanstack/react-query";

import { jobsApi, type GenerationJob, type Scene } from "@/lib/api";
import { useScopedKey } from "@/lib/use-scoped-key";

export type UseSceneJobsArgs = {
  projectId: string;
  activeScene?: Scene;
};

/**
 * 写作工作台：jobs 列表查询 + 当前 scene 三类任务（write/audit/rewrite）的派生状态。
 *
 * jobs query 自带轮询：当本项目存在 write/audit/rewrite 任务处于
 * queued/running 时每 1.5s 刷新一次，结束自动停止。
 */
export function useSceneJobs({ projectId, activeScene }: UseSceneJobsArgs) {
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
      return active ? 1500 : false;
    },
  });

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
