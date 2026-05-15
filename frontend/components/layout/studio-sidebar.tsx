"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Feather, ShieldCheck } from "lucide-react";
import { studioNav, adminNav } from "@/lib/routes";
import { isPlatformAdmin } from "@/lib/permissions";
import { cn } from "@/lib/cn";
import { useMockAuth } from "@/components/providers/mock-auth-provider";
import { PlanBadge } from "@/components/ui/badge";

export function StudioSidebar() {
  const pathname = usePathname();
  const { user } = useMockAuth();
  const adminVisible = isPlatformAdmin(user);

  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-[278px] flex-col bg-[#071327] p-4 text-white lg:flex">
      <Link href="/studio" className="flex items-center gap-3 border-b border-white/10 pb-5">
        <div className="grid size-12 place-items-center rounded-full border border-violet-400/50 bg-violet-500/15 text-violet-200">
          <Feather className="size-7" />
        </div>
        <div>
          <p className="text-xl font-black">NovelFlow AI</p>
          <p className="text-xs text-slate-300">自动小说生产平台</p>
        </div>
      </Link>

      <nav className="mt-5 space-y-2">
        {studioNav.map((item) => {
          const active = pathname === item.href || (item.href !== "/studio" && pathname.startsWith(item.href));
          const Icon = item.icon;
          return (
            <Link key={item.href} href={item.href} className={cn("flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold text-slate-200 transition hover:bg-white/10", active && "bg-indigo-500/80 text-white shadow-lg shadow-indigo-950/30")}>
              <Icon className="size-5" /> {item.label}
            </Link>
          );
        })}
      </nav>

      {adminVisible ? (
        <div className="mt-6 border-t border-white/10 pt-5">
          <p className="px-4 text-xs font-bold uppercase tracking-widest text-violet-200">管理员导航</p>
          <div className="mt-2 space-y-1">
            {adminNav.slice(0, 6).map((item) => {
              const Icon = item.icon;
              return (
                <Link key={item.href} href={item.href} className="flex items-center gap-3 rounded-xl px-4 py-2.5 text-sm font-medium text-slate-300 transition hover:bg-white/10 hover:text-white">
                  <Icon className="size-4" /> {item.label}
                </Link>
              );
            })}
          </div>
        </div>
      ) : null}

      <div className="mt-auto space-y-3">
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <PlanBadge plan={user.planCode} />
          <p className="mt-3 text-xs text-slate-300">剩余额度</p>
          <p className="mt-1 text-2xl font-black">68%</p>
          <div className="mt-3 h-2 rounded-full bg-white/10">
            <div className="h-2 w-[68%] rounded-full bg-gradient-to-r from-indigo-400 to-emerald-400" />
          </div>
        </div>
        <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/5 p-3">
          <div className="grid size-10 place-items-center rounded-full bg-slate-700 text-sm font-black">{user.name.slice(0, 1)}</div>
          <div className="min-w-0">
            <p className="truncate font-bold">{user.name}</p>
            <p className="truncate text-xs text-slate-400">{user.organizationName}</p>
          </div>
          {adminVisible ? <ShieldCheck className="ml-auto size-4 text-violet-300" /> : null}
        </div>
      </div>
    </aside>
  );
}
