"use client";

import { useMutation } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { TextField } from "@/components/ui/form-field";
import {
  type BiblePlotThread,
  type PlotThreadPayload,
  plotThreadsApi,
} from "@/lib/api";
import { ApiError } from "@/lib/http";

export type PlotThreadEditDialogProps = {
  projectId: string;
  thread: BiblePlotThread | null;
  onClose: () => void;
  onSaved: () => void;
};

export function PlotThreadEditDialog({
  projectId,
  thread,
  onClose,
  onSaved,
}: PlotThreadEditDialogProps) {
  const [form, setForm] = useState<PlotThreadPayload>({
    title: thread?.title ?? "",
    thread_type: thread?.thread_type ?? "main",
    description: thread?.description ?? "",
    status: thread?.status ?? "open",
  });
  const save = useMutation({
    mutationFn: () =>
      thread
        ? plotThreadsApi.update(projectId, thread.id, form)
        : plotThreadsApi.create(projectId, form),
    onSuccess: () => {
      toast.success(thread ? "剧情线已更新" : "已创建");
      onSaved();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "保存失败"),
  });
  const remove = useMutation({
    mutationFn: () => {
      if (!thread) throw new Error("no thread");
      return plotThreadsApi.remove(projectId, thread.id);
    },
    onSuccess: () => {
      toast.success("已删除");
      onSaved();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "删除失败"),
  });
  const set = <K extends keyof PlotThreadPayload>(k: K, v: PlotThreadPayload[K]) =>
    setForm((p) => ({ ...p, [k]: v }));
  return (
    <Modal title={thread ? "编辑剧情线" : "新增剧情线"} onClose={onClose}>
      <div className="space-y-3">
        <TextField label="名称" value={form.title} onChange={(v) => set("title", v)} />
        <div className="grid gap-3 md:grid-cols-2">
          <label className="block text-sm font-semibold text-slate-700">
            类型
            <select
              value={form.thread_type ?? "main"}
              onChange={(e) => set("thread_type", e.target.value)}
              className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
            >
              <option value="main">main 主线</option>
              <option value="sub">sub 副线</option>
              <option value="foreshadow">foreshadow 伏笔</option>
              <option value="background">background 背景</option>
            </select>
          </label>
          <label className="block text-sm font-semibold text-slate-700">
            状态
            <select
              value={form.status ?? "open"}
              onChange={(e) => set("status", e.target.value)}
              className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
            >
              <option value="open">open 进行中</option>
              <option value="closed">closed 已闭合</option>
              <option value="paused">paused 暂停</option>
            </select>
          </label>
        </div>
        <TextField label="描述" rows={4} value={form.description ?? ""} onChange={(v) => set("description", v)} />
        <div className="flex justify-between gap-2 pt-2">
          {thread ? (
            <Button
              variant="ghost"
              onClick={() => {
                if (window.confirm(`确认删除剧情线「${thread.title}」？`)) remove.mutate();
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
            <Button onClick={() => save.mutate()} disabled={save.isPending || !form.title.trim()}>
              {save.isPending ? "保存中…" : "保存"}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
