"use client";

import { useMutation } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { TextField } from "@/components/ui/form-field";
import {
  type BibleWorldItem,
  type WorldItemPayload,
  worldItemsApi,
} from "@/lib/api";
import { ApiError } from "@/lib/http";

export type WorldItemEditDialogProps = {
  projectId: string;
  item: BibleWorldItem | null;
  onClose: () => void;
  onSaved: () => void;
};

export function WorldItemEditDialog({
  projectId,
  item,
  onClose,
  onSaved,
}: WorldItemEditDialogProps) {
  const [form, setForm] = useState<WorldItemPayload>({
    type: item?.type ?? "rule",
    name: item?.name ?? "",
    description: item?.description ?? "",
    importance: item?.importance ?? "medium",
    is_hard_rule: item?.is_hard_rule ?? false,
  });
  const save = useMutation({
    mutationFn: () =>
      item
        ? worldItemsApi.update(projectId, item.id, form)
        : worldItemsApi.create(projectId, form),
    onSuccess: () => {
      toast.success(item ? "世界观条目已更新" : "已创建");
      onSaved();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "保存失败"),
  });
  const remove = useMutation({
    mutationFn: () => {
      if (!item) throw new Error("no item");
      return worldItemsApi.remove(projectId, item.id);
    },
    onSuccess: () => {
      toast.success("已删除");
      onSaved();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "删除失败"),
  });
  const set = <K extends keyof WorldItemPayload>(k: K, v: WorldItemPayload[K]) =>
    setForm((p) => ({ ...p, [k]: v }));
  return (
    <Modal title={item ? "编辑世界观条目" : "新增世界观条目"} onClose={onClose}>
      <div className="space-y-3">
        <div className="grid gap-3 md:grid-cols-2">
          <TextField label="类型（rule 规则 / location 地点 / faction 势力）" value={form.type} onChange={(v) => set("type", v)} />
          <TextField label="名称" value={form.name} onChange={(v) => set("name", v)} />
        </div>
        <TextField label="描述" rows={5} value={form.description ?? ""} onChange={(v) => set("description", v)} />
        <div className="grid gap-3 md:grid-cols-2">
          <label className="block text-sm font-semibold text-slate-700">
            重要性
            <select
              value={form.importance ?? "medium"}
              onChange={(e) => set("importance", e.target.value)}
              className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
            >
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
            </select>
          </label>
          <label className="mt-6 flex items-center gap-2 text-sm font-semibold text-slate-700">
            <input
              type="checkbox"
              checked={form.is_hard_rule ?? false}
              onChange={(e) => set("is_hard_rule", e.target.checked)}
            />
            硬规则（违反会触发审稿）
          </label>
        </div>
        <div className="flex justify-between gap-2 pt-2">
          {item ? (
            <Button
              variant="ghost"
              onClick={() => {
                if (window.confirm(`确认删除世界观条目「${item.name}」？`)) remove.mutate();
              }}
              disabled={remove.isPending}
              className="text-red-600 hover:bg-red-50"
            >
              <Trash2 className="size-4" /> 删除
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>
              取消
            </Button>
            <Button
              onClick={() => save.mutate()}
              disabled={save.isPending || !form.name.trim() || !form.type.trim()}
            >
              {save.isPending ? "保存中…" : "保存"}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
