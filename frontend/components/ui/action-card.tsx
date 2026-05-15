"use client";

import type { LucideIcon } from "lucide-react";
import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/cn";

export function ActionCard({ title, description, href, icon: Icon, tone = "violet" }: { title: string; description: string; href: string; icon: LucideIcon; tone?: "violet" | "blue" | "green" | "orange" }) {
  const colors = {
    violet: "from-violet-500 to-indigo-600",
    blue: "from-blue-500 to-sky-600",
    green: "from-emerald-500 to-green-600",
    orange: "from-orange-400 to-amber-500",
  };
  return (
    <Link href={href} className="group flex items-center gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
      <div className={cn("grid size-11 place-items-center rounded-2xl bg-gradient-to-br text-white", colors[tone])}>
        <Icon className="size-5" />
      </div>
      <div className="min-w-0 flex-1">
        <h3 className="font-bold text-slate-950">{title}</h3>
        <p className="truncate text-sm text-slate-500">{description}</p>
      </div>
      <ChevronRight className="size-5 text-slate-400 transition group-hover:translate-x-1 group-hover:text-indigo-600" />
    </Link>
  );
}
