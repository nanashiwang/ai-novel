type AlertTone = "rose" | "amber" | "green";

export type AlertItemProps = {
  tone: AlertTone;
  title: string;
  text: string;
};

const TONE_CLASS: Record<AlertTone, string> = {
  rose: "bg-rose-50 text-rose-700",
  amber: "bg-amber-50 text-amber-700",
  green: "bg-emerald-50 text-emerald-700",
};

export function AlertItem({ tone, title, text }: AlertItemProps) {
  return (
    <div className={`rounded-2xl p-4 ${TONE_CLASS[tone]}`}>
      <p className="font-bold">{title}</p>
      <p className="mt-1 text-sm opacity-80">{text}</p>
    </div>
  );
}
