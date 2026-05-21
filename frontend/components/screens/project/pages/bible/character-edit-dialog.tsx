"use client";

import { useMutation } from "@tanstack/react-query";
import { History, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { TextField } from "@/components/ui/form-field";
import {
  type BibleCharacter,
  type CharacterPayload,
  charactersApi,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { ApiError } from "@/lib/http";

import { CharacterRevisionHistory } from "./character-revision-history";

export type CharacterEditDialogProps = {
  projectId: string;
  character: BibleCharacter | null;
  onClose: () => void;
  onSaved: () => void;
};

type Tab = "edit" | "history";

export function CharacterEditDialog({
  projectId,
  character,
  onClose,
  onSaved,
}: CharacterEditDialogProps) {
  const [tab, setTab] = useState<Tab>("edit");
  const [form, setForm] = useState<CharacterPayload>({
    name: character?.name ?? "",
    role: character?.role ?? "",
    description: character?.description ?? "",
    personality: character?.personality ?? "",
    motivation: character?.motivation ?? "",
    secret: character?.secret ?? "",
    arc: character?.arc ?? "",
    relationships: character?.relationships ?? {},
    current_state: character?.current_state ?? {},
  });
  const save = useMutation({
    mutationFn: () =>
      character
        ? charactersApi.update(projectId, character.id, form)
        : charactersApi.create(projectId, form),
    onSuccess: () => {
      toast.success(character ? "人物已更新" : "人物已创建");
      onSaved();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "保存失败"),
  });
  const remove = useMutation({
    mutationFn: () => {
      if (!character) throw new Error("no character");
      return charactersApi.remove(projectId, character.id);
    },
    onSuccess: () => {
      toast.success("人物已删除");
      onSaved();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "删除失败"),
  });
  const set = <K extends keyof CharacterPayload>(k: K, v: CharacterPayload[K]) =>
    setForm((p) => ({ ...p, [k]: v }));
  const canShowHistory = Boolean(character);
  return (
    <Modal title={character ? "编辑人物" : "新增人物"} onClose={onClose}>
      {canShowHistory ? (
        <div className="mb-3 flex gap-1 rounded-xl bg-slate-100 p-1 text-sm">
          <button
            type="button"
            onClick={() => setTab("edit")}
            className={cn(
              "flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-1.5 font-semibold transition",
              tab === "edit" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500",
            )}
          >
            <Pencil className="size-3.5" /> 编辑
          </button>
          <button
            type="button"
            onClick={() => setTab("history")}
            className={cn(
              "flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-1.5 font-semibold transition",
              tab === "history" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500",
            )}
          >
            <History className="size-3.5" /> 历史版本
          </button>
        </div>
      ) : null}

      {canShowHistory && tab === "history" && character ? (
        <CharacterRevisionHistory
          projectId={projectId}
          characterId={character.id}
          onAfterChange={onSaved}
        />
      ) : (
        <div className="space-y-3">
          <div className="grid gap-3 md:grid-cols-2">
            <TextField label="姓名" value={form.name} onChange={(v) => set("name", v)} />
            <TextField label="定位（protagonist / antagonist / ...）" value={form.role ?? ""} onChange={(v) => set("role", v)} />
          </div>
          <TextField label="外貌 / 描写" rows={3} value={form.description ?? ""} onChange={(v) => set("description", v)} />
          <TextField label="性格" rows={2} value={form.personality ?? ""} onChange={(v) => set("personality", v)} />
          <TextField label="动机" rows={2} value={form.motivation ?? ""} onChange={(v) => set("motivation", v)} />
          <TextField label="秘密" rows={2} value={form.secret ?? ""} onChange={(v) => set("secret", v)} />
          <TextField label="人物弧光" rows={2} value={form.arc ?? ""} onChange={(v) => set("arc", v)} />
          <div className="flex justify-between gap-2 pt-2">
            {character ? (
              <Button
                variant="ghost"
                onClick={() => {
                  if (window.confirm(`确认删除人物「${character.name}」？`)) remove.mutate();
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
              <Button onClick={() => save.mutate()} disabled={save.isPending || !form.name.trim()}>
                {save.isPending ? "保存中…" : "保存"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}
