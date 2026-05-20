"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { adminApi, type AdminJobsFilter, type GenerationJob } from "@/lib/api";

const ADMIN_JOBS_KEY = ["admin", "jobs"] as const;

/**
 * 统一封装 admin/generation-jobs 列表查询。
 * 多个 Page（Dashboard / GenerationJobsPage）共用同一 queryKey 前缀，
 * 便于 mutation 后用 invalidateAdminJobs() 一次性失效。
 */
export function useAdminJobs(filter?: AdminJobsFilter) {
  return useQuery({
    queryKey: filter ? [...ADMIN_JOBS_KEY, filter] : ADMIN_JOBS_KEY,
    queryFn: () => adminApi.jobs(filter ?? {}) as Promise<GenerationJob[]>,
  });
}

export function useInvalidateAdminJobs() {
  const queryClient = useQueryClient();
  return useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ADMIN_JOBS_KEY });
  }, [queryClient]);
}
