"use client";

import { Bold, Code2, Image, Italic, Link2, List, Quote, Redo2, Save, Underline, Undo2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "./button";

const PLACEHOLDER =
  "尚未生成正文。请在写作工作台中执行生成任务，或导入既有章节内容。";

export function EditorMock() {
  const [value, setValue] = useState(PLACEHOLDER);
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center gap-1 border-b border-slate-100 bg-slate-50 px-4 py-3 text-slate-500">
        {[Undo2, Redo2, Bold, Italic, Underline, Code2, List, Quote, Link2, Image].map((Icon, index) => (
          <button key={index} type="button" className="grid size-8 place-items-center rounded-lg hover:bg-white hover:text-indigo-600">
            <Icon className="size-4" />
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2 text-xs text-emerald-600">
          <span className="size-2 rounded-full bg-emerald-500" /> 自动保存已开启
        </div>
      </div>
      <textarea
        className="min-h-[520px] w-full resize-none p-7 text-[15px] leading-9 text-slate-800 outline-none story-paper"
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 p-4">
        <p className="text-xs text-slate-500">当前场景字数：{value.length.toLocaleString()} · scene 是最小生成单位</p>
        <Button variant="secondary" onClick={() => toast.success("已保存为新的 draft_version")}> <Save className="size-4" /> 保存版本</Button>
      </div>
    </div>
  );
}
