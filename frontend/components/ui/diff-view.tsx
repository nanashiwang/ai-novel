"use client";

import { diffLines } from "diff";
import { useMemo } from "react";

/**
 * 简易行级 diff 视图。
 *
 * 用 jsdiff 的 diffLines 切出三类块：unchanged / added / removed，
 * 加色阶后行内展示。Sprint 4-B2 只做行级，未做字符级（intraline diff），
 * 等真正高频对比再升级。
 *
 * 输入约定纯文本（与 DraftVersion.content 一致）。
 */

type DiffViewProps = {
  oldContent: string;
  newContent: string;
  oldLabel?: string;
  newLabel?: string;
};

export function DiffView({
  oldContent,
  newContent,
  oldLabel = "旧版本",
  newLabel = "新版本",
}: DiffViewProps) {
  const parts = useMemo(
    () => diffLines(oldContent ?? "", newContent ?? ""),
    [oldContent, newContent],
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3 text-xs text-slate-500">
        <span>
          <span className="mr-2 rounded-md bg-rose-50 px-1.5 py-0.5 text-rose-700">
            −
          </span>
          {oldLabel}
        </span>
        <span>
          <span className="mr-2 rounded-md bg-emerald-50 px-1.5 py-0.5 text-emerald-700">
            +
          </span>
          {newLabel}
        </span>
      </div>
      <div className="max-h-[480px] overflow-y-auto rounded-2xl border border-slate-200 bg-white">
        <pre className="m-0 whitespace-pre-wrap p-4 font-mono text-xs leading-6">
          {parts.map((part, idx) => {
            if (part.added) {
              return (
                <span
                  key={idx}
                  className="block bg-emerald-50 text-emerald-900"
                >
                  {prefixLines(part.value, "+ ")}
                </span>
              );
            }
            if (part.removed) {
              return (
                <span key={idx} className="block bg-rose-50 text-rose-900">
                  {prefixLines(part.value, "− ")}
                </span>
              );
            }
            return (
              <span key={idx} className="block text-slate-700">
                {prefixLines(part.value, "  ")}
              </span>
            );
          })}
        </pre>
      </div>
    </div>
  );
}

function prefixLines(text: string, prefix: string): string {
  // jsdiff 的 part.value 通常以 "\n" 结尾且可能含多行。给每行加前缀。
  const trimmed = text.endsWith("\n") ? text.slice(0, -1) : text;
  if (!trimmed) return "";
  return trimmed
    .split("\n")
    .map((line) => prefix + line)
    .join("\n");
}
