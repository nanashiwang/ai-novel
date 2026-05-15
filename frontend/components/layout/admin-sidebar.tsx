"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Command } from "lucide-react";
import { adminNav } from "@/lib/routes";
import { cn } from "@/lib/cn";

export function AdminSidebar() {
  const pathname = usePathname();
  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-[284px] flex-col bg-slate-950 p-4 text-white lg:flex">
      <Link href="/admin" className="flex items-center gap-3 border-b border-white/10 pb-5">
        <div className="grid size-12 place-items-center rounded-2xl bg-gradient-to-br from-amber-400 to-orange-600 text-slate-950">
          <Command className="size-7" />
        </div>
        <div>
          <p className="text-xl font-black">Admin Console</p>
          <p className="text-xs text-slate-400">平台运营与审计后台</p>
        </div>
      </Link>
      <nav className="mt-5 space-y-1">
        {adminNav.map((item) => {
          const active = pathname === item.href;
          const Icon = item.icon;
          return (
            <Link key={item.href} href={item.href} className={cn("flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold text-slate-300 transition hover:bg-white/10 hover:text-white", active && "bg-white text-slate-950 shadow-sm hover:bg-white hover:text-slate-950")}>
              <Icon className="size-5" /> {item.label}
            </Link>
          );
        })}
      </nav>
      <Link href="/studio" className="mt-auto rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-300 transition hover:bg-white/10 hover:text-white">
        返回用户工作台
      </Link>
    </aside>
  );
}
