import { cn } from "@/lib/cn";

export function ProgressBar({ value, className, tone = "indigo" }: { value: number; className?: string; tone?: "indigo" | "green" | "orange" | "rose" }) {
  const color = {
    indigo: "bg-indigo-600",
    green: "bg-emerald-500",
    orange: "bg-orange-500",
    rose: "bg-rose-500",
  }[tone];
  return (
    <div className={cn("h-2 overflow-hidden rounded-full bg-slate-200", className)}>
      <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

export function QuotaProgress({ used, reserved, limit }: { used: number; reserved: number; limit: number }) {
  const usedPercent = limit ? (used / limit) * 100 : 0;
  const reservedPercent = limit ? (reserved / limit) * 100 : 0;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>已用 {used.toLocaleString()} / {limit.toLocaleString()}</span>
        <span>{Math.round(usedPercent)}%</span>
      </div>
      <div className="flex h-2 overflow-hidden rounded-full bg-slate-200">
        <div className="bg-emerald-500" style={{ width: `${Math.min(usedPercent, 100)}%` }} />
        <div className="bg-amber-400" style={{ width: `${Math.min(reservedPercent, 100 - usedPercent)}%` }} />
      </div>
      <p className="text-xs text-slate-500">预留中 {reserved.toLocaleString()}，任务完成后自动结算或释放。</p>
    </div>
  );
}
