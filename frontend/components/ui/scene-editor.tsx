"use client";

import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useEffect } from "react";

/**
 * 单场景正文编辑器（Tiptap headless）。
 *
 * 约定：对外接口是纯文本（与后端 draft_versions.content 一致）。
 * 内部把空行 `\n\n` 视为段落分隔；编辑器输出时通过 getText({blockSeparator})
 * 反向还原。这避免了"前端存 HTML、后端存纯文本"的契约分裂，代价是
 * Sprint 4-B 暂时不支持加粗/斜体等富文本（StarterKit 默认支持但保存会被
 * 序列化丢弃）。后续 Sprint 引入"富文本草稿存储"时再升级。
 */

type SceneEditorProps = {
  content: string;
  onChange?: (plain: string) => void;
  editable?: boolean;
};

const HTML_ESCAPE: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
};

function escapeHtml(s: string): string {
  return s.replace(/[&<>]/g, (c) => HTML_ESCAPE[c] ?? c);
}

function plainToHtml(text: string): string {
  if (!text) return "";
  return text
    .split(/\n{2,}/)
    .map((para) => `<p>${escapeHtml(para).replace(/\n/g, "<br/>")}</p>`)
    .join("");
}

export function SceneEditor({ content, onChange, editable = true }: SceneEditorProps) {
  const editor = useEditor({
    extensions: [StarterKit],
    content: plainToHtml(content),
    editable,
    // Tiptap v3 + Next.js App Router：避免 SSR 期间访问 DOM。
    immediatelyRender: false,
    onUpdate: ({ editor: ed }) => {
      onChange?.(ed.getText({ blockSeparator: "\n\n" }));
    },
  });

  // 外部 content 变化（如切换历史版本）时同步到编辑器；
  // 比较时把当前编辑器内容也转回纯文本，避免无差别 setContent 触发循环。
  useEffect(() => {
    if (!editor) return;
    const current = editor.getText({ blockSeparator: "\n\n" });
    if (current === content) return;
    editor.commands.setContent(plainToHtml(content), { emitUpdate: false });
  }, [content, editor]);

  // editable 切换（如版本预览模式）时同步
  useEffect(() => {
    if (!editor) return;
    editor.setEditable(editable);
  }, [editable, editor]);

  return (
    <EditorContent
      editor={editor}
      className="prose prose-slate max-h-[480px] max-w-none overflow-y-auto rounded-2xl bg-white p-4 text-sm leading-7 text-slate-800 focus:outline-none"
    />
  );
}
