"use client";

import { Button } from "@/components/ui/button";

import type { CreativePrefs } from "./creative-prefs";

export type CreativePrefsCardProps = {
  prefs: CreativePrefs;
  onChange: (next: CreativePrefs) => void;
  advanced: boolean;
  onToggleAdvanced: () => void;
  defaultsExplain: boolean;
  onToggleDefaultsExplain: () => void;
};

export function CreativePrefsCard({
  prefs,
  onChange,
  advanced,
  onToggleAdvanced,
  defaultsExplain,
  onToggleDefaultsExplain,
}: CreativePrefsCardProps) {
  const update = <K extends keyof CreativePrefs>(key: K, value: CreativePrefs[K]) => {
    onChange({ ...prefs, [key]: value });
  };
  return (
    <div className="space-y-4 rounded-2xl border border-indigo-100 bg-indigo-50/40 p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-bold text-indigo-900">创作偏好（可选，全部留空走默认）</p>
        <Button size="sm" variant="ghost" onClick={onToggleDefaultsExplain}>
          {defaultsExplain ? "隐藏默认说明" : "查看默认策略"}
        </Button>
      </div>
      {defaultsExplain ? (
        <div className="rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-600 leading-6">
          <p className="font-bold text-slate-700">字段全部留空时，系统会按以下默认策略推断：</p>
          <ul className="ml-4 mt-1 list-disc">
            <li>从项目标题 / 类型 / 目标章节数推断故事类型</li>
            <li>主角原型基于通用文学范式，偏内敛 + 有明确��机</li>
            <li>避免血腥、政治隐喻、色情等高风险内容</li>
            <li>温度默认 0.7，平衡稳定与发挥</li>
            <li>自动化默认「标准」：关键里程碑（圣经 / 大纲 / 前 3 章）会要求确认</li>
            <li>审稿默认「标准」严格度</li>
          </ul>
        </div>
      ) : null}

      {/* 基础偏好 */}
      <label className="block text-sm font-semibold text-slate-700">
        创作意图 / 主题
        <textarea
          rows={2}
          value={prefs.topic}
          onChange={(e) => update("topic", e.target.value)}
          placeholder="比如：在记忆可以被买卖的城市里，一名档案修复师追查妹妹失踪案。"
          className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
        />
      </label>
      <label className="block text-sm font-semibold text-slate-700">
        主角原型 / 期望
        <textarea
          rows={2}
          value={prefs.protagonist_archetype}
          onChange={(e) => update("protagonist_archetype", e.target.value)}
          placeholder="比如：失忆的天才档案管理员，内敛、对真相有偏执的执念。"
          className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
        />
      </label>
      <div className="grid gap-4 md:grid-cols-2">
        <label className="block text-sm font-semibold text-slate-700">
          目标读者
          <select
            value={prefs.target_reader}
            onChange={(e) => update("target_reader", e.target.value)}
            className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
          >
            <option value="">默认</option>
            <option value="男频读者">男频读者</option>
            <option value="女频读者">女频读者</option>
            <option value="青少年">青少年</option>
            <option value="成人悬疑读者">成人悬疑读者</option>
            <option value="轻小说读者">轻小说读者</option>
          </select>
        </label>
        <label className="block text-sm font-semibold text-slate-700">
          故事基调
          <select
            value={prefs.story_tone}
            onChange={(e) => update("story_tone", e.target.value)}
            className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
          >
            <option value="">默认</option>
            <option value="轻松">轻松</option>
            <option value="治愈">治愈</option>
            <option value="热血">热血</option>
            <option value="悬疑">悬疑</option>
            <option value="黑暗">黑暗</option>
            <option value="史诗">史诗</option>
            <option value="压抑">压抑</option>
          </select>
        </label>
      </div>
      <label className="block text-sm font-semibold text-slate-700">
        禁忌主题（逗号分隔，绝对不要出现）
        <input
          value={prefs.forbidden_themes}
          onChange={(e) => update("forbidden_themes", e.target.value)}
          placeholder="血腥, 政治隐喻"
          className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
        />
      </label>

      <div className="flex items-center justify-between">
        <p className="text-xs font-bold text-slate-500">高级偏好</p>
        <Button size="sm" variant="ghost" onClick={onToggleAdvanced}>
          {advanced ? "收起" : "展开"}
        </Button>
      </div>
      {advanced ? (
        <div className="space-y-4">
          <label className="block text-sm font-semibold text-slate-700">
            参考作品（逗号分隔，仅做风格参考）
            <input
              value={prefs.reference_works}
              onChange={(e) => update("reference_works", e.target.value)}
              placeholder="盗梦空间, 银翼杀手"
              className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
            />
          </label>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="block text-sm font-semibold text-slate-700">
              节奏偏好
              <select
                value={prefs.pacing}
                onChange={(e) => update("pacing", e.target.value)}
                className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
              >
                <option value="">默认</option>
                <option value="快节奏强钩子">快节奏强钩子</option>
                <option value="中等节奏">中等节奏</option>
                <option value="慢热铺垫">慢热铺垫</option>
              </select>
            </label>
            <label className="block text-sm font-semibold text-slate-700">
              结局倾向
              <select
                value={prefs.ending_lean}
                onChange={(e) => update("ending_lean", e.target.value)}
                className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
              >
                <option value="">默认</option>
                <option value="开放式">开放式</option>
                <option value="圆满">圆满</option>
                <option value="悲剧">悲剧</option>
                <option value="反转">反转</option>
                <option value="系列续作">系列续作</option>
              </select>
            </label>
            <label className="block text-sm font-semibold text-slate-700">
              自动化程度
              <select
                value={prefs.automation_level}
                onChange={(e) => update("automation_level", e.target.value)}
                className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
              >
                <option value="cautious">谨慎 · 每步都确认</option>
                <option value="standard">标准 · 关键节点确认</option>
                <option value="auto">全自动 · 系统自动推进</option>
              </select>
            </label>
            <label className="block text-sm font-semibold text-slate-700">
              审稿严格度
              <select
                value={prefs.audit_strictness}
                onChange={(e) => update("audit_strictness", e.target.value)}
                className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
              >
                <option value="loose">宽松</option>
                <option value="standard">标准</option>
                <option value="strict">严格</option>
              </select>
            </label>
          </div>
          <label className="block text-sm font-semibold text-slate-700">
            创作温度（0 = 保守稳定，1.5 = 高发挥）：{prefs.temperature.toFixed(2)}
            <input
              type="range"
              min={0}
              max={1.5}
              step={0.05}
              value={prefs.temperature}
              onChange={(e) => update("temperature", Number(e.target.value))}
              className="mt-2 w-full"
            />
          </label>
        </div>
      ) : null}
    </div>
  );
}
