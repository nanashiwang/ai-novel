"use client";

import { Pencil } from "lucide-react";

import { Badge } from "@/components/ui/badge";

export type EditableItemProps = {
  title: string;
  badge?: string;
  text: string;
  onEdit: () => void;
};

export function EditableItem({ title, badge, text, onEdit }: EditableItemProps) {
  return (
    <div className="group relative rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="font-bold text-slate-950">{title}</p>
        <div className="flex items-center gap-2">
          {badge ? <Badge tone="slate">{badge}</Badge> : null}
          <button
            type="button"
            onClick={onEdit}
            className="rounded-md p-1 text-slate-400 opacity-0 transition group-hover:opacity-100 hover:bg-slate-100 hover:text-slate-700"
            aria-label="编辑"
          >
            <Pencil className="size-3.5" />
          </button>
        </div>
      </div>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-500">{text || "—"}</p>
    </div>
  );
}
