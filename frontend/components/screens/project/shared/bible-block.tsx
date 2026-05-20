export type BibleBlockProps = {
  title: string;
  text: string;
};

/**
 * 一个简单的「标题 + 文本」展示块。
 * 跨多个 project Page（Bible / Characters / Outline / Writing）复用。
 */
export function BibleBlock({ title, text }: BibleBlockProps) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <p className="text-sm font-black text-slate-950">{title}</p>
      <p className="mt-2 text-sm leading-6 text-slate-600">{text}</p>
    </div>
  );
}
