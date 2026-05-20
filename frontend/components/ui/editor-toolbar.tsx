"use client";

import type { Editor } from "@tiptap/react";
import {
  Bold,
  Heading2,
  Heading3,
  Italic,
  List,
  ListOrdered,
  Quote,
  Redo2,
  Strikethrough,
  Undo2,
} from "lucide-react";

import { cn } from "@/lib/cn";

type ToolbarButtonProps = {
  icon: typeof Bold;
  label: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
};

function ToolbarButton({ icon: Icon, label, active, disabled, onClick }: ToolbarButtonProps) {
  return (
    <button
      type="button"
      onMouseDown={(e) => e.preventDefault()} // 避免编辑器失焦
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      aria-pressed={active ?? false}
      className={cn(
        "grid size-8 place-items-center rounded-lg text-slate-500 transition",
        "hover:bg-white hover:text-indigo-600",
        active ? "bg-indigo-50 text-indigo-600" : "",
        disabled ? "cursor-not-allowed opacity-40 hover:bg-transparent hover:text-slate-500" : "",
      )}
    >
      <Icon className="size-4" />
    </button>
  );
}

export type EditorToolbarProps = {
  editor: Editor | null;
  /** 字符数（用于右侧统计显示）；undefined 则不展示 */
  characterCount?: number;
  /** 字符数目标（如场景目标字数），有则展示 当前/目标 */
  characterTarget?: number;
};

export function EditorToolbar({ editor, characterCount, characterTarget }: EditorToolbarProps) {
  if (!editor) return null;

  const can = editor.can();
  return (
    <div className="flex flex-wrap items-center gap-1 border-b border-slate-100 bg-slate-50 px-3 py-2">
      <ToolbarButton
        icon={Undo2}
        label="撤销 (Cmd/Ctrl+Z)"
        disabled={!can.undo()}
        onClick={() => editor.chain().focus().undo().run()}
      />
      <ToolbarButton
        icon={Redo2}
        label="重做 (Cmd/Ctrl+Shift+Z)"
        disabled={!can.redo()}
        onClick={() => editor.chain().focus().redo().run()}
      />
      <span className="mx-1 h-5 w-px bg-slate-200" aria-hidden />
      <ToolbarButton
        icon={Bold}
        label="加粗 (Cmd/Ctrl+B)"
        active={editor.isActive("bold")}
        onClick={() => editor.chain().focus().toggleBold().run()}
      />
      <ToolbarButton
        icon={Italic}
        label="斜体 (Cmd/Ctrl+I)"
        active={editor.isActive("italic")}
        onClick={() => editor.chain().focus().toggleItalic().run()}
      />
      <ToolbarButton
        icon={Strikethrough}
        label="删除线"
        active={editor.isActive("strike")}
        onClick={() => editor.chain().focus().toggleStrike().run()}
      />
      <span className="mx-1 h-5 w-px bg-slate-200" aria-hidden />
      <ToolbarButton
        icon={Heading2}
        label="标题 2"
        active={editor.isActive("heading", { level: 2 })}
        onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
      />
      <ToolbarButton
        icon={Heading3}
        label="标题 3"
        active={editor.isActive("heading", { level: 3 })}
        onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
      />
      <ToolbarButton
        icon={List}
        label="无序列表"
        active={editor.isActive("bulletList")}
        onClick={() => editor.chain().focus().toggleBulletList().run()}
      />
      <ToolbarButton
        icon={ListOrdered}
        label="有序列表"
        active={editor.isActive("orderedList")}
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
      />
      <ToolbarButton
        icon={Quote}
        label="引��"
        active={editor.isActive("blockquote")}
        onClick={() => editor.chain().focus().toggleBlockquote().run()}
      />
      {typeof characterCount === "number" ? (
        <div className="ml-auto text-xs text-slate-500">
          {characterCount.toLocaleString()}
          {typeof characterTarget === "number" && characterTarget > 0
            ? ` / ${characterTarget.toLocaleString()} 字`
            : " 字"}
        </div>
      ) : null}
    </div>
  );
}
