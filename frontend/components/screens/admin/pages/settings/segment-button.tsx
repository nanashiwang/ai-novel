"use client";

import { CheckCircle2 } from "lucide-react";

export type SegmentButtonProps = {
  active: boolean;
  disabled: boolean;
  title: string;
  desc: string;
  onClick: () => void;
};

export function SegmentButton({ active, disabled, title, desc, onClick }: SegmentButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`flex min-h-20 items-center justify-between rounded-xl border px-4 text-left transition disabled:cursor-not-allowed disabled:opacity-60 ${
        active
          ? "border-indigo-500 bg-indigo-50 text-indigo-900"
          : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
      }`}
    >
      <span>
        <span className="block font-bold">{title}</span>
        <span className="mt-1 block text-sm opacity-70">{desc}</span>
      </span>
      {active ? <CheckCircle2 className="size-5 shrink-0" /> : null}
    </button>
  );
}
