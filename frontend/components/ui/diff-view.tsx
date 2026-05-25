"use client";

import { diffLines } from "diff";
import { useMemo } from "react";

import { cn } from "@/lib/cn";

/**
 * 代码风格的行级 diff 视图。
 *
 * - 删除行：红色底色 + `-`
 * - 新增行：绿色底色 + `+`
 * - 未变行：白底 + 空前缀
 */

type DiffViewProps = {
  oldContent: string;
  newContent: string;
  oldLabel?: string;
  newLabel?: string;
};

export type DiffRow = {
  kind: "added" | "removed" | "unchanged";
  text: string;
  oldLineNumber: number | null;
  newLineNumber: number | null;
};

export function DiffView({
  oldContent,
  newContent,
  oldLabel = "旧版本",
  newLabel = "新版本",
}: DiffViewProps) {
  const rows = useMemo(
    () => buildDiffRows(oldContent ?? "", newContent ?? ""),
    [oldContent, newContent],
  );
  const removedCount = rows.filter((row) => row.kind === "removed").length;
  const addedCount = rows.filter((row) => row.kind === "added").length;
  const hasChanges = removedCount > 0 || addedCount > 0;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-flex items-center gap-1">
            <span className="rounded-md bg-rose-100 px-1.5 py-0.5 font-mono font-bold text-rose-700">
              -
            </span>
            {oldLabel}
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="rounded-md bg-emerald-100 px-1.5 py-0.5 font-mono font-bold text-emerald-700">
              +
            </span>
            {newLabel}
          </span>
        </div>
        <span>{removedCount} 删除 / {addedCount} 新增</span>
      </div>

      {!hasChanges && rows.length > 0 ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          两个版本正文没有可标记的行级差异；若字数不同，请检查版本元数据是否已重新统计。
        </div>
      ) : null}

      <div className="max-h-[560px] overflow-auto rounded-2xl border border-slate-200 bg-white shadow-inner">
        <div className="sticky top-0 z-10 grid min-w-[720px] grid-cols-[4rem_4rem_2.5rem_minmax(0,1fr)] border-b border-slate-200 bg-slate-100/95 px-3 py-2 font-mono text-[11px] font-semibold uppercase tracking-wide text-slate-500 backdrop-blur">
          <span>旧行</span>
          <span>新行</span>
          <span />
          <span>内容</span>
        </div>
        <div className="min-w-[720px] font-mono text-xs leading-6">
          {rows.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-slate-500">
              两个版本内容都为空。
            </div>
          ) : (
            rows.map((row, idx) => (
              <div
                key={`${row.kind}-${row.oldLineNumber ?? "x"}-${row.newLineNumber ?? "x"}-${idx}`}
                className={cn(
                  "grid grid-cols-[4rem_4rem_2.5rem_minmax(0,1fr)] border-l-4 px-3",
                  rowClassName(row.kind),
                )}
              >
                <span className="select-none text-right text-slate-400">
                  {row.oldLineNumber ?? ""}
                </span>
                <span className="select-none text-right text-slate-400">
                  {row.newLineNumber ?? ""}
                </span>
                <span className={cn("select-none text-center font-bold", prefixClassName(row.kind))}>
                  {prefixFor(row.kind)}
                </span>
                <code className="whitespace-pre-wrap break-words pl-2">
                  {row.text || " "}
                </code>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export function buildDiffRows(oldContent: string, newContent: string): DiffRow[] {
  let oldLineNumber = 1;
  let newLineNumber = 1;
  const rows: DiffRow[] = [];

  for (const part of diffLines(oldContent ?? "", newContent ?? "")) {
    const lines = splitDiffLines(part.value);
    for (const line of lines) {
      if (part.added) {
        rows.push({
          kind: "added",
          text: line,
          oldLineNumber: null,
          newLineNumber: newLineNumber,
        });
        newLineNumber += 1;
      } else if (part.removed) {
        rows.push({
          kind: "removed",
          text: line,
          oldLineNumber: oldLineNumber,
          newLineNumber: null,
        });
        oldLineNumber += 1;
      } else {
        rows.push({
          kind: "unchanged",
          text: line,
          oldLineNumber: oldLineNumber,
          newLineNumber: newLineNumber,
        });
        oldLineNumber += 1;
        newLineNumber += 1;
      }
    }
  }

  return rows;
}

function splitDiffLines(text: string): string[] {
  if (!text) return [];
  const withoutTrailingNewline = text.endsWith("\n") ? text.slice(0, -1) : text;
  return withoutTrailingNewline.split("\n");
}

function rowClassName(kind: DiffRow["kind"]): string {
  if (kind === "added") {
    return "border-emerald-400 bg-emerald-50 text-emerald-950";
  }
  if (kind === "removed") {
    return "border-rose-400 bg-rose-50 text-rose-950";
  }
  return "border-transparent bg-white text-slate-700";
}

function prefixClassName(kind: DiffRow["kind"]): string {
  if (kind === "added") return "text-emerald-700";
  if (kind === "removed") return "text-rose-700";
  return "text-slate-400";
}

function prefixFor(kind: DiffRow["kind"]): string {
  if (kind === "added") return "+";
  if (kind === "removed") return "-";
  return " ";
}
