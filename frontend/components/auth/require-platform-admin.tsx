"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/components/providers/auth-provider";
import { isPlatformAdmin } from "@/lib/permissions";

/**
 * 包裹仅平台管理员可访问的页面（如 /admin 下所有路由）。
 */
export function RequirePlatformAdmin({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/auth/login");
      return;
    }
    if (!isPlatformAdmin(user)) {
      router.replace("/studio");
    }
  }, [user, loading, router]);

  if (loading || !user || !isPlatformAdmin(user)) {
    return <div className="grid h-screen place-items-center text-slate-500">校验权限中…</div>;
  }
  return <>{children}</>;
}
