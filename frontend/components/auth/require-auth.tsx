"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/components/providers/auth-provider";

/**
 * 包裹需要登录的页面。未登录将重定向到 /auth/login。
 */
export function RequireAuth({
  children,
  fallback,
}: {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/auth/login");
    }
  }, [user, loading, router]);

  if (loading) {
    return (
      fallback ?? (
        <div className="grid h-screen place-items-center text-slate-500">加载中…</div>
      )
    );
  }
  if (!user) return null;
  return <>{children}</>;
}
