import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

const toneClass = {
  violet: "from-violet-500 to-indigo-600 text-white",
  blue: "from-blue-500 to-sky-600 text-white",
  green: "from-emerald-500 to-green-600 text-white",
  orange: "from-orange-400 to-amber-500 text-white",
  rose: "from-rose-500 to-pink-600 text-white",
  slate: "from-slate-700 to-slate-950 text-white",
};

export function StatCard({
  label,
  value,
  delta,
  icon: Icon,
  tone = "violet",
}: {
  label: string;
  value: string;
  delta?: string;
  icon: LucideIcon;
  tone?: keyof typeof toneClass;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className={cn("grid size-12 place-items-center rounded-2xl bg-gradient-to-br shadow-sm", toneClass[tone])}>
          <Icon className="size-6" />
        </div>
        <div className="h-10 w-20 rounded-xl bg-gradient-to-r from-transparent via-slate-100 to-indigo-100" />
      </div>
      <p className="mt-4 text-sm font-medium text-slate-500">{label}</p>
      <div className="mt-1 flex items-end justify-between gap-2">
        <p className="text-3xl font-black tracking-tight text-slate-950">{value}</p>
        {delta ? <p className="text-xs font-semibold text-emerald-600">{delta}</p> : null}
      </div>
    </div>
  );
}
