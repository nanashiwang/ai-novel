"use client";

import { FileArchive } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SceneEditor } from "@/components/ui/scene-editor";
import type { ContentFormat, DraftVersion } from "@/lib/api";

export type SceneEditorCardProps = {
  version: DraftVersion;
  editable: boolean;
  isSaving: boolean;
  /** 保存时拿到 markdown content + 实际格式（编辑器始终升级为 markdown） */
  onSave: (content: string, format: ContentFormat) => void;
  onAutoSave?: (content: string, format: ContentFormat) => void;
  /** 场景目标字数（来自 scene.target_words 等），用于编辑器工具栏字数进度 */
  characterTarget?: number;
};

/**
 * Editor + dirty 检测 + 保存按钮 + 自动保存（debounce 15s）的子组件。
 *
 * 父组件用 `key={version.id}` 控制 remount，避免在 useEffect 中直接 setState
 * 同步 props → state（React 19 的 set-state-in-effect 反模式）。
 *
 * Sprint 4-C 起：编辑器升级为富文本（markdown）。版本初始内容按 version.content_format
 * 加载；任何用户编辑产出的内容统一写为 'markdown'，避免格式抖动。
 */
export function SceneEditorCard({
  version,
  editable,
  isSaving,
  onSave,
  onAutoSave,
  characterTarget,
}: SceneEditorCardProps) {
  const [content, setContent] = useState(version.content);
  const [format, setFormat] = useState<ContentFormat>(version.content_format);
  // dirty 判定：内容字符串变化 || 格式从 'text' 升级为 'markdown'
  const isDirty = content !== version.content || format !== version.content_format;

  // 用 ref 持有最新 onAutoSave 引��，避免 useCallback 链反复重置 debounce timer。
  // ref 赋值在 useEffect 内完成以符合 React 19 的 refs-in-render 规则。
  const autoSaveRef = useRef(onAutoSave);
  useEffect(() => {
    autoSaveRef.current = onAutoSave;
  }, [onAutoSave]);

  // 自动保存：editable 且 dirty 时启动 15s debounce；任意编辑动作都会重置 timer。
  useEffect(() => {
    if (!editable || !isDirty) return;
    const timer = setTimeout(() => {
      autoSaveRef.current?.(content, format);
    }, 15_000);
    return () => clearTimeout(timer);
  }, [content, editable, format, isDirty]);

  return (
    <>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          {isDirty ? <Badge tone="violet">未保存</Badge> : null}
          {!editable ? <Badge tone="amber">预览历史版本</Badge> : null}
          {editable && isDirty && onAutoSave ? (
            <span className="text-xs text-slate-400">15s 后自动保存</span>
          ) : null}
        </div>
        {editable ? (
          <Button
            variant="secondary"
            onClick={() => onSave(content, format)}
            disabled={!isDirty || isSaving}
          >
            <FileArchive className="size-4" />
            保存版本
          </Button>
        ) : null}
      </div>
      <SceneEditor
        content={content}
        contentFormat={format}
        onChange={(next, nextFormat) => {
          setContent(next);
          setFormat(nextFormat);
        }}
        editable={editable}
        characterTarget={characterTarget}
      />
    </>
  );
}
