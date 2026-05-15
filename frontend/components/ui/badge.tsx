import { cn } from "@/lib/cn";
import type { JobStatus, ProjectStatus, WorkflowStepStatus } from "@/types";

type Tone = "slate" | "blue" | "green" | "amber" | "rose" | "violet" | "orange";

const toneClass: Record<Tone, string> = {
  slate: "bg-slate-100 text-slate-700 ring-slate-200",
  blue: "bg-blue-50 text-blue-700 ring-blue-200",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  amber: "bg-amber-50 text-amber-700 ring-amber-200",
  rose: "bg-rose-50 text-rose-700 ring-rose-200",
  violet: "bg-violet-50 text-violet-700 ring-violet-200",
  orange: "bg-orange-50 text-orange-700 ring-orange-200",
};

export function Badge({ children, tone = "slate", className }: { children: React.ReactNode; tone?: Tone; className?: string }) {
  return <span className={cn("inline-flex items-center rounded-lg px-2 py-1 text-xs font-semibold ring-1", toneClass[tone], className)}>{children}</span>;
}

const projectTone: Record<ProjectStatus, Tone> = {
  created: "slate",
  bible_generating: "violet",
  bible_ready: "blue",
  outline_generating: "violet",
  outline_ready: "green",
  drafting: "blue",
  auditing: "orange",
  rewriting: "amber",
  completed: "green",
  exported: "green",
};

const jobTone: Record<JobStatus | WorkflowStepStatus, Tone> = {
  queued: "slate",
  running: "blue",
  succeeded: "green",
  failed: "rose",
  cancelled: "amber",
  pending: "slate",
  completed: "green",
};

export function StatusBadge({ status }: { status: ProjectStatus | JobStatus | WorkflowStepStatus | string }) {
  const tone = (projectTone as Record<string, Tone>)[status] ?? (jobTone as Record<string, Tone>)[status] ?? "slate";
  return <Badge tone={tone}>{status}</Badge>;
}

export function PlanBadge({ plan }: { plan: string }) {
  return <Badge tone={plan === "Enterprise" ? "amber" : "violet"}>{plan} 套餐</Badge>;
}
