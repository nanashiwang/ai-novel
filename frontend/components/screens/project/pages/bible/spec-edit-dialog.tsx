"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { ListField, TextField } from "@/components/ui/form-field";
import { type Bible, type NovelSpecPayload, specApi } from "@/lib/api";
import { ApiError } from "@/lib/http";

export type SpecEditDialogProps = {
  projectId: string;
  spec: NonNullable<Bible["spec"]>;
  onClose: () => void;
  onSaved: () => void;
};

export function SpecEditDialog({ projectId, spec, onClose, onSaved }: SpecEditDialogProps) {
  const [form, setForm] = useState<NovelSpecPayload>({
    premise: spec.premise,
    theme: spec.theme,
    genre: spec.genre,
    tone: spec.tone,
    target_reader: spec.target_reader,
    narrative_pov: spec.narrative_pov,
    style_guide: spec.style_guide,
    constraints: spec.constraints,
    continuity_rules: [],
  });
  const save = useMutation({
    mutationFn: () => specApi.upsert(projectId, form),
    onSuccess: () => {
      toast.success("核心设定已更新");
      onSaved();
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "保存失败"),
  });
  const set = <K extends keyof NovelSpecPayload>(k: K, v: NovelSpecPayload[K]) =>
    setForm((p) => ({ ...p, [k]: v }));
  return (
    <Modal title="编辑核心设定" onClose={onClose}>
      <div className="space-y-3">
        <TextField label="Premise" rows={3} value={form.premise ?? ""} onChange={(v) => set("premise", v)} />
        <div className="grid gap-3 md:grid-cols-2">
          <TextField label="Theme" value={form.theme ?? ""} onChange={(v) => set("theme", v)} />
          <TextField label="Genre" value={form.genre ?? ""} onChange={(v) => set("genre", v)} />
          <TextField label="Tone" value={form.tone ?? ""} onChange={(v) => set("tone", v)} />
          <TextField
            label="POV"
            value={form.narrative_pov ?? ""}
            onChange={(v) => set("narrative_pov", v)}
          />
          <TextField
            label="Target Reader"
            value={form.target_reader ?? ""}
            onChange={(v) => set("target_reader", v)}
          />
        </div>
        <TextField
          label="Style Guide"
          rows={3}
          value={form.style_guide ?? ""}
          onChange={(v) => set("style_guide", v)}
        />
        <ListField
          label="约束 / 规则"
          values={form.constraints ?? []}
          onChange={(v) => set("constraints", v)}
        />
        <ListField
          label="连贯性规则"
          values={form.continuity_rules ?? []}
          onChange={(v) => set("continuity_rules", v)}
        />
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? "保存中…" : "保存"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
