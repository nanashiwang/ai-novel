"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { adminApi } from "@/lib/api";

const ADMIN_AUDIT_LOGS_KEY = ["admin", "audit-logs"] as const;

/**
 * 统一封装 admin/audit-logs 查询。
 * 后端目前返回 unknown[]，泛型由调用端自行 narrow。
 *
 * 收敛 queryKey 后：mutation（plan create/update、user 修改等）
 * 调 useInvalidateAdminAuditLogs() 即可失效。
 */
export function useAdminAuditLogs<T = unknown>() {
  return useQuery({
    queryKey: ADMIN_AUDIT_LOGS_KEY,
    queryFn: () => adminApi.auditLogs() as Promise<T[]>,
  });
}

export function useInvalidateAdminAuditLogs() {
  const queryClient = useQueryClient();
  return useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ADMIN_AUDIT_LOGS_KEY });
  }, [queryClient]);
}
