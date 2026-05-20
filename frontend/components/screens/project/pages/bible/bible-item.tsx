import { Badge } from "@/components/ui/badge";

export type BibleItemProps = {
  title: string;
  badge?: string;
  text: string;
};

export function BibleItem({ title, badge, text }: BibleItemProps) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="font-bold text-slate-950">{title}</p>
        {badge ? <Badge tone="slate">{badge}</Badge> : null}
      </div>
      <p className="mt-2 text-sm leading-6 text-slate-500">{text || "—"}</p>
    </div>
  );
}
