"use client";

import { FileArchive } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SceneEditor } from "@/components/ui/scene-editor";
import type { DraftVersion } from "@/lib/api";

export type SceneEditorCardProps = {
  version: DraftVersion;
  editable: boolean;
  isSaving: boolean;
  onSave: (content: string) => void;
  onAutoSave?: (content: string) => void;
};

/**
 * Editor + dirty 检测 + 保存按钮 + 自动保存（debounce 15s）的子组件。
 *
 * 父组件用 `key={version.id}` 控制 remount，避免在 useEffect 中直接 setState
 * 同步 props → state（React 19 的 set-state-in-effect 反模式）。
 */
export function SceneEditorCard({
  version,
  editable,
  isSaving,
  onSave,
  onAutoSave,
}: SceneEditorCardProps) {
  const [content, setContent] = useState(version.content);
  const isDirty = content !== version.content;

  // 用 ref 持有最新 onAutoSave 引用，避免 useCallback 链反复重置 debounce timer。
  // ref 赋值在 useEffect 内完成以符合 React 19 的 refs-in-render 规则。
  const autoSaveRef = useRef(onAutoSave);
  useEffect(() => {
    autoSaveRef.current = onAutoSave;
  }, [onAutoSave]);

  // 自动保存：editable 且 dirty 时启动 15s debounce；任意编辑动作都会重置 timer。
  useEffect(() => {
    if (!editable || !isDirty) return;
    const timer = setTimeout(() => {
      autoSaveRef.current?.(content);
    }, 15_000);
    return () => clearTimeout(timer);
  }, [content, editable, isDirty]);

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
            onClick={() => onSave(content)}
            disabled={!isDirty || isSaving}
          >
            <FileArchive className="size-4" />
            保存版本
          </Button>
        ) : null}
      </div>
      <SceneEditor content={content} onChange={setContent} editable={editable} />
    </>
  );
}
