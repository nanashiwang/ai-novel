"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Feather, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo, useState } from "react";

import { useAuth } from "@/components/providers/auth-provider";
import { PlanBadge } from "@/components/ui/badge";
import { quotaApi, projectsApi } from "@/lib/api";
import { cn } from "@/lib/cn";
import { findActiveNavHref } from "@/lib/nav-active";
import { isPlatformAdmin } from "@/lib/permissions";
import { resolveProjectNav, studioNav } from "@/lib/routes";
import { useScopedKey } from "@/lib/use-scoped-key";

const PROJECT_PATH_RE = /^\/studio\/projects\/([^/]+)/;

export function StudioSidebar() {
  const pathname = usePathname();
  const { user } = useAuth();
  const adminVisible = isPlatformAdmin(user);
  const activeHref = findActiveNavHref(pathname, studioNav);
  // 仅当 URL 中存在 projectId 且不是 "new" / "" 这类 sentinel 才展开
  const matched = pathname.match(PROJECT_PATH_RE);
  const currentProjectId =
    matched && matched[1] && matched[1] !== "new" ? matched[1] : null;

  const { data: quotas } = useQuery({
    queryKey: useScopedKey("quotas"),
    queryFn: () => quotaApi.list(),
    enabled: !!user,
  });
  const { data: currentProject } = useQuery({
    queryKey: useScopedKey("project", currentProjectId ?? "_"),
    queryFn: () => projectsApi.get(currentProjectId as string),
    enabled: !!user && !!currentProjectId,
  });

  const wordQuota = quotas?.find((q) => q.quota_key === "monthly_generated_words");
  const usedPct = wordQuota
    ? Math.min(
        100,
        Math.round(((wordQuota.used_value + wordQuota.reserved_value) / Math.max(wordQuota.limit_value, 1)) * 100),
      )
    : 0;

  // 项目二级菜单：在项目上下文中默认展开；用户可手动折叠。
  const [projectMenuOpen, setProjectMenuOpen] = useState(true);
  const projectChildren = useMemo(
    () => (currentProjectId ? resolveProjectNav(currentProjectId) : []),
    [currentProjectId],
  );

  if (!user) return null;

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

      <nav className="mt-5 flex-1 space-y-1 overflow-y-auto pr-1">
        {studioNav.map((item) => {
          const active = activeHref === item.href;
          const Icon = item.icon;
          const isProjectsGroup = item.href === "/studio/projects";
          const showChildren = isProjectsGroup && currentProjectId;
          return (
            <div key={item.href}>
              <div
                className={cn(
                  "flex items-center rounded-xl text-sm font-semibold text-slate-200 transition hover:bg-white/10",
                  active && "bg-indigo-500/80 text-white shadow-lg shadow-indigo-950/30",
                )}
              >
                <Link href={item.href} className="flex flex-1 items-center gap-3 px-4 py-3">
                  <Icon className="size-5" /> {item.label}
                </Link>
                {showChildren ? (
                  <button
                    type="button"
                    aria-label={projectMenuOpen ? "折叠项目菜单" : "展开项目菜单"}
                    onClick={() => setProjectMenuOpen((open) => !open)}
                    className="grid size-9 place-items-center rounded-r-xl text-slate-300 hover:text-white"
                  >
                    {projectMenuOpen ? (
                      <ChevronDown className="size-4" />
                    ) : (
                      <ChevronRight className="size-4" />
                    )}
                  </button>
                ) : null}
              </div>
              {showChildren && projectMenuOpen ? (
                <div className="my-1 ml-3 space-y-0.5 border-l border-white/10 pl-3">
                  {currentProject ? (
                    <p className="px-2 py-1.5 text-xs text-slate-400">
                      <span className="truncate">{currentProject.title}</span>
                    </p>
                  ) : null}
                  {projectChildren.map((child) => {
                    // 子菜单激活规则：完全匹配 path；总览（项目根）需要精确等于
                    const isOverview =
                      child.href === `/studio/projects/${currentProjectId}`;
                    const childActive = isOverview
                      ? pathname === child.href
                      : pathname === child.href || pathname.startsWith(child.href + "/");
                    const ChildIcon = child.icon;
                    return (
                      <Link
                        key={child.href}
                        href={child.href}
                        className={cn(
                          "flex items-center gap-2.5 rounded-lg px-3 py-2 text-xs font-semibold text-slate-300 transition hover:bg-white/10 hover:text-white",
                          childActive && "bg-indigo-500/30 text-white",
                        )}
                      >
                        <ChildIcon className="size-3.5" /> {child.label}
                      </Link>
                    );
                  })}
                </div>
              ) : null}
            </div>
          );
        })}
      </nav>

      <div className="mt-3 space-y-3">
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <PlanBadge plan={user.plan_code as never} />
          <p className="mt-3 text-xs text-slate-300">月生成额度使用</p>
          <p className="mt-1 text-2xl font-black">{usedPct}%</p>
          <div className="mt-3 h-2 rounded-full bg-white/10">
            <div
              className="h-2 rounded-full bg-gradient-to-r from-indigo-400 to-emerald-400"
              style={{ width: `${usedPct}%` }}
            />
          </div>
          {adminVisible ? (
            <Link
              href="/admin"
              className="mt-4 flex items-center justify-between rounded-xl border border-violet-300/20 bg-violet-500/15 px-3 py-2.5 text-sm font-bold text-violet-100 transition hover:border-violet-200/40 hover:bg-violet-500/25"
            >
              <span className="flex items-center gap-2">
                <ShieldCheck className="size-4" />
                管理员工作台
              </span>
              <span className="text-xs text-violet-200">进入</span>
            </Link>
          ) : null}
        </div>
        <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/5 p-3">
          <div className="grid size-10 place-items-center rounded-full bg-slate-700 text-sm font-black">
            {user.display_name.slice(0, 1)}
          </div>
          <div className="min-w-0">
            <p className="truncate font-bold">{user.display_name}</p>
            <p className="truncate text-xs text-slate-400">{user.organization_name}</p>
          </div>
          {adminVisible ? <ShieldCheck className="ml-auto size-4 text-violet-300" /> : null}
        </div>
      </div>
    </aside>
  );
}
