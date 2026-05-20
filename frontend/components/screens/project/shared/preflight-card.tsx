"use client";

import { CheckCircle2, TimerReset, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { ProgressBar } from "@/components/ui/progress";
import type { PreflightReport } from "@/lib/api";

export type PreflightCardProps = {
  report: PreflightReport;
};

/**
 * 生成前检查卡片：展示 quota / entitlement / checks。
 * 被 BiblePage 和 WritingWorkspacePage 共用。
 */
export function PreflightCard({ report }: PreflightCardProps) {
  const remaining = report.quota_available;
  const limit = report.quota_limit;
  const pct = limit > 0 ? Math.min(100, Math.round(((limit - remaining) / limit) * 100)) : 0;
  return (
    <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-bold text-slate-950">生成前检查</p>
        <div className="flex items-center gap-2 text-xs">
          <Badge tone="violet">{report.plan_code}</Badge>
          <span className="text-slate-500">
            剩余 {remaining.toLocaleString()} / {limit.toLocaleString()} 字
          </span>
        </div>
      </div>
      <ProgressBar value={pct} tone={remaining >= report.estimate_words ? "green" : "orange"} />
      <ul className="space-y-2 text-sm">
        {report.checks.map((c, i) => (
          <li key={i} className="flex items-start gap-2">
            {c.level === "ok" ? (
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" />
            ) : c.level === "warn" ? (
              <TimerReset className="mt-0.5 size-4 shrink-0 text-amber-600" />
            ) : (
              <XCircle className="mt-0.5 size-4 shrink-0 text-rose-600" />
            )}
            <div>
              <p className="font-semibold text-slate-800">{c.label}</p>
              {c.detail ? <p className="text-slate-500">{c.detail}</p> : null}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
