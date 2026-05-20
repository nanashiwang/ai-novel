import { CheckCircle2 } from "lucide-react";

/** 列出本次生成会产出什么，给用户预期感。 */
export function WillGenerateList() {
  const items = [
    "故事前提（Premise）",
    "核心主题（Theme）",
    "主线冲突 / 张力源",
    "主角与关键人物原型",
    "世界观基础规则",
    "剧情线 / 主要伏笔",
    "文风规则与叙事视角",
    "禁忌与硬约束",
  ];
  return (
    <div className="rounded-2xl border border-emerald-100 bg-emerald-50/40 p-4">
      <p className="text-sm font-bold text-emerald-900">本次将生成</p>
      <ul className="mt-2 grid gap-1.5 text-sm text-emerald-900/80 md:grid-cols-2">
        {items.map((it) => (
          <li key={it} className="flex items-center gap-2">
            <CheckCircle2 className="size-3.5" /> {it}
          </li>
        ))}
      </ul>
    </div>
  );
}
