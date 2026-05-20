"use client";

import { Badge } from "@/components/ui/badge";

/**
 * ContextBuilder Inspector 显示的单段摘要结构。
 * 与 backend/app/workflows/activities.py::run_scene_writing 返回的
 * output_payload.context_summary 对齐。
 */
export type ContextSummaryEntry = {
  label: string;
  trusted: boolean;
  token_budget: number;
  estimated_tokens: number;
  truncated: boolean;
  preview: string;
};

export type ContextInspectorProps = {
  summary?: {
    context_summary?: ContextSummaryEntry[];
    context_total_tokens?: number;
  } | null;
};

export function ContextInspector({ summary }: ContextInspectorProps) {
  const segments = summary?.context_summary ?? [];
  if (segments.length === 0) return null;
  return (
    <div className="space-y-2 border-t border-slate-100 pt-3 text-xs text-slate-500">
      <div className="flex items-center justify-between">
        <p className="font-bold text-slate-950">ContextBuilder Inspector</p>
        <span className="text-xs">
          总 tokens：{summary?.context_total_tokens ?? 0}
        </span>
      </div>
      {segments.map((seg) => (
        <details key={seg.label} className="rounded-md border border-slate-100">
          <summary className="cursor-pointer px-2 py-1">
            <span className="font-mono text-slate-700">{seg.label}</span>
            <span className="ml-2 text-slate-400">
              {seg.estimated_tokens}/{seg.token_budget}t
            </span>
            {!seg.trusted ? (
              <Badge tone="amber" className="ml-2">
                untrusted
              </Badge>
            ) : null}
            {seg.truncated ? (
              <Badge tone="rose" className="ml-2">
                truncated
              </Badge>
            ) : null}
          </summary>
          <pre className="m-0 whitespace-pre-wrap px-2 pb-2 text-xs text-slate-500">
            {seg.preview}
            {seg.truncated ? "…" : ""}
          </pre>
        </details>
      ))}
    </div>
  );
}
