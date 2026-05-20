export type AdminTitleProps = {
  title: string;
  desc: string;
};

export function AdminTitle({ title, desc }: AdminTitleProps) {
  return (
    <div>
      <h1 className="text-3xl font-black text-slate-950">{title}</h1>
      <p className="mt-1 text-slate-500">{desc}</p>
    </div>
  );
}
