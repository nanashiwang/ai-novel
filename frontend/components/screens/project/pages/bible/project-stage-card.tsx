"use client";

import { CheckCircle2, TimerReset } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

export type ProjectStageCardProps = {
  projectId: string;
  projectStatus: string;
  hasSpec: boolean;
  characterCount: number;
  worldItemCount: number;
  plotThreadCount: number;
};

/** 项目阶段卡片：展示当���里程碑 + 推荐下一步。 */
export function ProjectStageCard({
  projectId,
  projectStatus,
  hasSpec,
  characterCount,
  worldItemCount,
  plotThreadCount,
}: ProjectStageCardProps) {
  // 里程碑顺序：created → bible → outline → scenes → drafting → completed
  const milestones = [
    { key: "bible", label: "故事圣经", done: hasSpec },
    {
      key: "outline",
      label: "章节大纲",
      done: ["outlined", "scenes_planning", "scenes_planned", "drafting", "completed"].includes(
        projectStatus,
      ),
    },
    {
      key: "scenes",
      label: "场景计划",
      done: ["scenes_planned", "drafting", "completed"].includes(projectStatus),
    },
    {
      key: "drafting",
      label: "章节正文",
      done: ["drafting", "completed"].includes(projectStatus),
    },
    { key: "completed", label: "全书完结", done: projectStatus === "completed" },
  ];
  return (
    <Card>
      <CardContent className="space-y-4 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm text-slate-500">当前阶段</p>
            <p className="mt-1 text-lg font-black text-slate-950">
              {projectStatus} {hasSpec ? "·  圣经就绪" : ""}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm text-slate-600">
            <span>���物 {characterCount}</span>
            <span>世界观 {worldItemCount}</span>
            <span>剧情线 {plotThreadCount}</span>
          </div>
        </div>
        <div className="flex items-center gap-2 overflow-x-auto">
          {milestones.map((m, i) => (
            <div key={m.key} className="flex items-center gap-2">
              <div
                className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-bold ${
                  m.done
                    ? "bg-emerald-100 text-emerald-800"
                    : "bg-slate-100 text-slate-500"
                }`}
              >
                {m.done ? <CheckCircle2 className="size-3.5" /> : <TimerReset className="size-3.5" />}
                {m.label}
              </div>
              {i < milestones.length - 1 ? (
                <span className="text-slate-300">›</span>
              ) : null}
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-400">
          项目 ID: {projectId}
        </p>
      </CardContent>
    </Card>
  );
}
