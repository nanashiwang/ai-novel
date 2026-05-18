"use client";

import { Bell, Crown, LogOut, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { Badge, PlanBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ProgressBar } from "@/components/ui/progress";
import { quotaApi } from "@/lib/api";
import { isPlatformAdmin } from "@/lib/permissions";
import { useScopedKey } from "@/lib/use-scoped-key";

export function Topbar({ mode = "studio" }: { mode?: "studio" | "admin" }) {
  const router = useRouter();
  const { user, logout } = useAuth();
  const admin = isPlatformAdmin(user);

  const { data: quotas } = useQuery({
    queryKey: useScopedKey("quotas"),
    queryFn: () => quotaApi.list(),
    enabled: !!user,
  });

  const wordQuota = quotas?.find((q) => q.quota_key === "monthly_generated_words");
  const usedPct = wordQuota
    ? Math.round(((wordQuota.used_value + wordQuota.reserved_value) / Math.max(wordQuota.limit_value, 1)) * 100)
    : 0;
  const remaining = wordQuota ? wordQuota.limit_value - wordQuota.used_value : 0;

  if (!user) return null;

  return (
    <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/85 px-4 py-3 backdrop-blur-xl lg:px-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">
            {mode === "admin" ? "Platform" : "Studio"}
          </p>
          <div className="mt-1 flex items-center gap-2">
            <Badge tone={admin ? "amber" : "blue"}>{user.platform_role}</Badge>
            <span className="text-sm font-semibold text-slate-600">{user.email}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="hidden items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-2 shadow-sm md:flex">
            <UserRound className="size-5 text-indigo-600" />
            <div>
              <p className="text-xs text-slate-500">当前组织</p>
              <p className="text-sm font-bold text-slate-950">{user.organization_name}</p>
            </div>
          </div>
          <div className="hidden items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-2 shadow-sm md:flex">
            <Crown className="size-5 text-indigo-600" />
            <PlanBadge plan={user.plan_code as never} />
          </div>
          {wordQuota ? (
            <div className="hidden min-w-56 rounded-2xl border border-slate-200 bg-white px-4 py-2 shadow-sm xl:block">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-500">
                <span>剩余字数</span>
                <span>{remaining.toLocaleString()} 字（{100 - usedPct}%）</span>
              </div>
              <ProgressBar value={usedPct} className="mt-2" tone="green" />
            </div>
          ) : null}
          <button
            type="button"
            className="relative grid size-10 place-items-center rounded-xl border border-slate-200 bg-white text-slate-600 shadow-sm"
          >
            <Bell className="size-5" />
          </button>
          <Button
            variant="secondary"
            onClick={async () => {
              await logout();
              router.push("/auth/login");
            }}
          >
            <LogOut className="size-4" /> 退出
          </Button>
          {admin && mode !== "admin" ? (
            <Link href="/admin">
              <Button variant="dark">Admin</Button>
            </Link>
          ) : null}
        </div>
      </div>
    </header>
  );
}
