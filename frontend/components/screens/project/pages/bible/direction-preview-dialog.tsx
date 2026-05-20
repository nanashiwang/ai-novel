"use client";

import { useQuery } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { projectsApi, type StoryDirection } from "@/lib/api";

import { type CreativePrefs, splitTags } from "./creative-prefs";

export type DirectionPreviewDialogProps = {
  projectId: string;
  prefs: CreativePrefs;
  onClose: () => void;
  onPick: (d: StoryDirection) => void;
};

export function DirectionPreviewDialog({
  projectId,
  prefs,
  onClose,
  onPick,
}: DirectionPreviewDialogProps) {
  const { data, isPending, isError } = useQuery({
    queryKey: ["preview-directions", projectId, prefs.topic, prefs.protagonist_archetype],
    queryFn: () =>
      projectsApi.previewDirections(projectId, {
        topic: prefs.topic || undefined,
        protagonist_archetype: prefs.protagonist_archetype || undefined,
        reference_works: splitTags(prefs.reference_works),
        forbidden_themes: splitTags(prefs.forbidden_themes),
      }),
  });
  return (
    <Modal title="预览 3 个创作方向" onClose={onClose}>
      <p className="mb-3 text-sm text-slate-500">
        从下面 3 个方向中挑一个最贴近你的预期，点「选用」后会自动回填到「创作意图」字段。
      </p>
      {isPending ? (
        <p className="py-6 text-center text-sm text-slate-500">加载中…</p>
      ) : isError || !data ? (
        <p className="py-6 text-center text-sm text-rose-500">加载失败</p>
      ) : (
        <div className="space-y-3">
          {data.directions.map((d) => (
            <div
              key={d.name}
              className={`rounded-2xl border p-4 ${
                d.recommended ? "border-indigo-300 bg-indigo-50/40" : "border-slate-200"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <p className="font-bold text-slate-950">
                  {d.name} {d.recommended ? <Badge tone="violet">推荐</Badge> : null}
                </p>
                <Button size="sm" onClick={() => onPick(d)}>
                  选用
                </Button>
              </div>
              <p className="mt-2 text-sm text-slate-700">{d.summary}</p>
              {d.selling_points.length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {d.selling_points.map((sp) => (
                    <Badge key={sp} tone="green">
                      {sp}
                    </Badge>
                  ))}
                </div>
              ) : null}
              {d.risk ? <p className="mt-2 text-xs text-amber-700">⚠ {d.risk}</p> : null}
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}
