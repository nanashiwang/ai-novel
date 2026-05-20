"use client";

import CharacterCount from "@tiptap/extension-character-count";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useEffect } from "react";

import type { ContentFormat } from "@/lib/api";

import { EditorToolbar } from "./editor-toolbar";
import { editorToMarkdown, markdownToHtml, textToHtml } from "./markdown";

/**
 * 单场景正文编辑器（Tiptap headless）。
 *
 * 对外接口（接收/输出）取决于 `contentFormat`：
 * - "text"     —— 历史纯文本路径，按段落 `\n\n` 切分；输出仍是纯文本
 * - "markdown" —— 新写入路径，输出 markdown 字符串
 *
 * 切换路径不需要外部协调：传入的 content 字符串 + format 一同变化即可。
 *
 * onChange 第二参数告知调用方"实际保存格式"——
 * - 老版本（'text'）一旦被编辑会自然升级为 'markdown'（用户期望未来格式保留）
 * - autosave / 手动保存的 mutation 把这个 format 一起写入数据库
 */

export type SceneEditorProps = {
  content: string;
  contentFormat?: ContentFormat;
  onChange?: (content: string, format: ContentFormat) => void;
  editable?: boolean;
  /** 目标字数；展示在工具栏右侧 进度提示，可选 */
  characterTarget?: number;
};

export function SceneEditor({
  content,
  contentFormat = "text",
  onChange,
  editable = true,
  characterTarget,
}: SceneEditorProps) {
  const initialHtml =
    contentFormat === "markdown" ? markdownToHtml(content) : textToHtml(content);

  const editor = useEditor({
    extensions: [StarterKit, CharacterCount],
    content: initialHtml,
    editable,
    // Tiptap v3 + Next.js App Router：避免 SSR 期间访问 DOM。
    immediatelyRender: false,
    onUpdate: ({ editor: ed }) => {
      if (!onChange) return;
      // 编辑器输出统一升级为 markdown——纯文本路径只在"加载旧数据"时存在，
      // 一旦用户产生编辑就视为升级，避免格式抖动。
      onChange(editorToMarkdown(ed), "markdown");
    },
  });

  // 外部 content 变化（如切换历史版本）时同步到编辑器；
  // 比较时把当前编辑器内容也转回当前 format，避免无差别 setContent 触发循环。
  useEffect(() => {
    if (!editor) return;
    const currentExternal =
      contentFormat === "markdown" ? editorToMarkdown(editor) : editor.getText({ blockSeparator: "\n\n" });
    if (currentExternal === content) return;
    const html = contentFormat === "markdown" ? markdownToHtml(content) : textToHtml(content);
    editor.commands.setContent(html, { emitUpdate: false });
  }, [content, contentFormat, editor]);

  // editable 切换（如版本预览模式）时同步
  useEffect(() => {
    if (!editor) return;
    editor.setEditable(editable);
  }, [editable, editor]);

  // characterCount.characters() 即字符数；中文按字符算（与字数一致）
  const characterCount = editor?.storage.characterCount?.characters?.() as number | undefined;

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      {editable ? (
        <EditorToolbar
          editor={editor}
          characterCount={characterCount}
          characterTarget={characterTarget}
        />
      ) : null}
      <EditorContent
        editor={editor}
        className="prose prose-slate max-h-[480px] max-w-none overflow-y-auto p-4 text-sm leading-7 text-slate-800 focus:outline-none"
      />
    </div>
  );
}
