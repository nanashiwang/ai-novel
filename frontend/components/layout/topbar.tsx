"use client";

import Link from "next/link";
import { Bell, Crown, UserRound } from "lucide-react";
import { useMockAuth } from "@/components/providers/mock-auth-provider";
import { isPlatformAdmin } from "@/lib/permissions";
import { Button } from "@/components/ui/button";
import { Badge, PlanBadge } from "@/components/ui/badge";
import { ProgressBar } from "@/components/ui/progress";

export function Topbar({ mode = "studio" }: { mode?: "studio" | "admin" }) {
  const { user, role, toggleRole } = useMockAuth();
  const admin = isPlatformAdmin(user);
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/85 px-4 py-3 backdrop-blur-xl lg:px-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">{mode === "admin" ? "Platform" : "Studio"}</p>
          <div className="mt-1 flex items-center gap-2">
            <Badge tone={admin ? "amber" : "blue"}>{user.platformRole}</Badge>
            <span className="text-sm font-semibold text-slate-600">{user.email}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="hidden items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-2 shadow-sm md:flex">
            <UserRound className="size-5 text-indigo-600" />
            <div>
              <p className="text-xs text-slate-500">当前组织</p>
              <p className="text-sm font-bold text-slate-950">{user.organizationName}</p>
            </div>
          </div>
          <div className="hidden items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-2 shadow-sm md:flex">
            <Crown className="size-5 text-indigo-600" />
            <PlanBadge plan={user.planCode} />
          </div>
          <div className="hidden min-w-56 rounded-2xl border border-slate-200 bg-white px-4 py-2 shadow-sm xl:block">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-500">
              <span>剩余额度</span><span>682,450 字（68%）</span>
            </div>
            <ProgressBar value={68} className="mt-2" tone="green" />
          </div>
          <button type="button" className="relative grid size-10 place-items-center rounded-xl border border-slate-200 bg-white text-slate-600 shadow-sm">
            <Bell className="size-5" />
            <span className="absolute -right-1 -top-1 grid size-4 place-items-center rounded-full bg-rose-500 text-[10px] font-bold text-white">5</span>
          </button>
          <Button variant="secondary" onClick={toggleRole}>{role === "admin" ? "切到普通用户" : "切到 super_admin"}</Button>
          {admin ? <Link href="/admin"><Button variant={mode === "admin" ? "dark" : "primary"}>Admin</Button></Link> : null}
        </div>
      </div>
    </header>
  );
}
