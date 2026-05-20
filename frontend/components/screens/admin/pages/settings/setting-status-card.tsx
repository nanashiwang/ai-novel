"use client";

import type { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

export type SettingTone = "green" | "amber" | "rose";

export type SettingStatusCardProps = {
  icon: LucideIcon;
  label: string;
  value: string;
  tone: SettingTone;
};

const TONE_CLASS: Record<SettingTone, string> = {
  green: "bg-emerald-50 text-emerald-700",
  amber: "bg-amber-50 text-amber-700",
  rose: "bg-rose-50 text-rose-700",
};

export function SettingStatusCard({ icon: Icon, label, value, tone }: SettingStatusCardProps) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3">
        <span className={`grid size-10 shrink-0 place-items-center rounded-xl ${TONE_CLASS[tone]}`}>
          <Icon className="size-5" />
        </span>
        <div className="min-w-0">
          <p className="text-xs font-bold uppercase text-slate-400">{label}</p>
          <p className="truncate text-sm font-bold text-slate-950">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}
