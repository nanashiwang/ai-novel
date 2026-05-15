import { Check, Circle, Loader2, X } from "lucide-react";
import { cn } from "@/lib/cn";
import type { WorkflowStep } from "@/types";

export function WorkflowSteps({ steps }: { steps: WorkflowStep[] }) {
  return (
    <div className="grid gap-3 md:grid-cols-6">
      {steps.map((step, index) => {
        const Icon = step.status === "completed" ? Check : step.status === "running" ? Loader2 : step.status === "failed" ? X : Circle;
        return (
          <div key={step.id} className="relative rounded-2xl border border-slate-200 bg-white p-4">
            {index < steps.length - 1 ? <span className="absolute left-[calc(100%-0.5rem)] top-7 hidden h-0.5 w-6 bg-slate-200 md:block" /> : null}
            <div className="flex items-center gap-2">
              <div
                className={cn(
                  "grid size-8 place-items-center rounded-full",
                  step.status === "completed" && "bg-emerald-100 text-emerald-700",
                  step.status === "running" && "bg-indigo-100 text-indigo-700",
                  step.status === "pending" && "bg-slate-100 text-slate-400",
                  step.status === "failed" && "bg-rose-100 text-rose-700",
                )}
              >
                <Icon className={cn("size-4", step.status === "running" && "animate-spin")} />
              </div>
              <div>
                <p className="text-sm font-bold text-slate-900">{step.name}</p>
                <p className="text-xs text-slate-500">{step.status}</p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
