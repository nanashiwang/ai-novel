"use client";

import { useRouter } from "next/navigation";
import { CheckCircle2, FileText, Gauge, Lightbulb, Wand2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { QuotaProgress } from "@/components/ui/progress";
import { quotas } from "@/lib/mock-data";

const steps = ["基础信息", "题材与读者", "生成策略", "确认额度"];

export function CreateProjectPage() {
  const router = useRouter();
  const [activeStep, setActiveStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const quota = quotas[0];

  const create = () => {
    setLoading(true);
    setTimeout(() => {
      toast.success("项目已创建，并启动故事圣经 workflow（mock）");
      router.push("/studio/projects/demo-project");
    }, 700);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-black text-slate-950">新建小说项目</h1>
        <p className="mt-1 text-slate-500">4 步向导：收集设定、预估额度、创建后生成故事圣经。</p>
      </div>
      <div className="grid gap-6 xl:grid-cols-[0.72fr_1.28fr]">
        <Card>
          <CardHeader><CardTitle>创建向导</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            {steps.map((step, index) => (
              <button key={step} type="button" onClick={() => setActiveStep(index)} className={`flex w-full items-center gap-3 rounded-2xl border p-4 text-left transition ${activeStep === index ? "border-indigo-300 bg-indigo-50" : "border-slate-200 hover:bg-slate-50"}`}>
                <div className={`grid size-9 place-items-center rounded-full text-sm font-bold ${activeStep >= index ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-500"}`}>{activeStep > index ? <CheckCircle2 className="size-5" /> : index + 1}</div>
                <div><p className="font-bold text-slate-950">{step}</p><p className="text-xs text-slate-500">{index === 0 ? "标题、创意、目标字数" : index === 1 ? "类型、文风、目标读者" : index === 2 ? "自动生成预览与禁忌内容" : "套餐、权益、额度检查"}</p></div>
              </button>
            ))}
            <div className="rounded-2xl bg-slate-50 p-4">
              <div className="mb-2 flex items-center gap-2 font-bold text-slate-950"><Gauge className="size-5 text-indigo-600" /> 套餐和额度检查</div>
              <QuotaProgress used={quota.usedValue} reserved={quota.reservedValue} limit={quota.limitValue} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between"><CardTitle>项目表单</CardTitle><Badge tone="violet">Pro 权益可用</Badge></CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="小说标题" defaultValue="雾都归档人" />
              <Field label="小说类型" defaultValue="悬疑 · 都市" />
              <Field label="目标字数" defaultValue="300000" />
              <Field label="目标章节数" defaultValue="48" />
              <Field label="叙事视角" defaultValue="第三人称有限视角" />
              <Field label="目标读者" defaultValue="都市悬疑 / 档案题材读者" />
            </div>
            <label className="block text-sm font-bold text-slate-700">一句话创意<textarea className="mt-2 min-h-24 w-full rounded-2xl border border-slate-200 p-4 outline-none focus:border-indigo-500" defaultValue="失忆档案修复师在雾都地下库房中发现自己被抹除的家族案卷。" /></label>
            <label className="block text-sm font-bold text-slate-700">文风<textarea className="mt-2 min-h-24 w-full rounded-2xl border border-slate-200 p-4 outline-none focus:border-indigo-500" defaultValue="冷峻克制，细节密集，空间氛围潮湿压迫。" /></label>
            <label className="block text-sm font-bold text-slate-700">禁忌内容<textarea className="mt-2 min-h-20 w-full rounded-2xl border border-slate-200 p-4 outline-none focus:border-indigo-500" defaultValue="不要提前揭示归档计划主谋；不得混淆人物记忆状态。" /></label>
            <div className="grid gap-4 md:grid-cols-2">
              <PreviewCard icon={Lightbulb} title="创建后自动生成预览" text="故事圣经、核心冲突、人物初始关系与世界规则。" />
              <PreviewCard icon={Wand2} title="预计额度" text="预留 20,000 字；完成后按实际输出结算。" />
            </div>
            <div className="flex flex-wrap justify-end gap-3">
              <Button variant="secondary" onClick={() => toast.info("草稿已保存（mock）")}>保存草稿</Button>
              <Button variant="ghost" onClick={() => router.push("/studio/projects")}>取消</Button>
              <Button onClick={create} disabled={loading}>{loading ? "创建中..." : "创建项目并生成故事圣经"}</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Field({ label, defaultValue }: { label: string; defaultValue: string }) {
  return <label className="block text-sm font-bold text-slate-700">{label}<input className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-4 outline-none focus:border-indigo-500" defaultValue={defaultValue} /></label>;
}

function PreviewCard({ icon: Icon, title, text }: { icon: typeof FileText; title: string; text: string }) {
  return <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><Icon className="size-5 text-indigo-600" /><p className="mt-2 font-bold text-slate-950">{title}</p><p className="mt-1 text-sm text-slate-500">{text}</p></div>;
}
