import type { DraftVersion } from "@/lib/api";

export function labelForVersion(versions: DraftVersion[], versionId: string): string {
  const idx = versions.findIndex((v) => v.id === versionId);
  if (idx < 0) return "未知版本";
  return `第 ${versions.length - idx} 版`;
}
