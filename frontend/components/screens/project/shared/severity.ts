export type SeverityTone = "rose" | "amber" | "slate";

export function severityTone(severity: string): SeverityTone {
  switch (severity) {
    case "high":
      return "rose";
    case "medium":
      return "amber";
    default:
      return "slate";
  }
}

export function severityClass(severity: string): string {
  switch (severity) {
    case "high":
      return "border-rose-200 bg-rose-50/40";
    case "medium":
      return "border-amber-200 bg-amber-50/40";
    default:
      return "border-slate-200";
  }
}
