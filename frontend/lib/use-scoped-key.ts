"use client";

/**
 * 工具 hook：把当前组织 id 注入 queryKey，避免切租后读到上一个组织缓存。
 *
 * 使用：
 *   const key = useScopedKey("projects");
 *   useQuery({ queryKey: key, queryFn: () => projectsApi.list() });
 */
import { useAuth } from "@/components/providers/auth-provider";

export function useScopedKey(...parts: ReadonlyArray<string | number | undefined | null>) {
  const { user } = useAuth();
  return ["org", user?.organization_id ?? "anon", ...parts] as const;
}
