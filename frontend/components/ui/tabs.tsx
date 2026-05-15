import Link from "next/link";
import { cn } from "@/lib/cn";

export function Tabs({ tabs, activeHref }: { tabs: { label: string; href: string }[]; activeHref: string }) {
  return (
    <div className="flex flex-wrap gap-2 rounded-2xl border border-slate-200 bg-white p-2 shadow-sm">
      {tabs.map((tab) => (
        <Link
          key={tab.href}
          href={tab.href}
          className={cn(
            "rounded-xl px-4 py-2 text-sm font-semibold transition",
            activeHref === tab.href ? "bg-indigo-600 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100 hover:text-slate-950",
          )}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  );
}
