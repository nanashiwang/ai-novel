"use client";

import type { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

export type StatJobProps = {
  label: string;
  value: number;
  icon: LucideIcon;
};

export function StatJob({ label, value, icon: Icon }: StatJobProps) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4">
        <div className="grid size-12 place-items-center rounded-2xl bg-indigo-50 text-indigo-600">
          <Icon className="size-6" />
        </div>
        <div>
          <p className="text-sm text-slate-500">{label}</p>
          <p className="text-3xl font-black text-slate-950">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}
