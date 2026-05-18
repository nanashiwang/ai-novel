"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileText, Gauge, Lightbulb, Wand2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { QuotaProgress } from "@/components/ui/progress";
import { projectsApi, quotaApi } from "@/lib/api";
import { ApiError } from "@/lib/http";
import { useScopedKey } from "@/lib/use-scoped-key";

const steps = ["基础信息", "题材与读者", "生成策略", "确认额度"];

type FormState = {
  title: string;
  genre: string;
  target_word_count: number;
  target_chapter_count: number;
  premise: string;
  style: string;
};

const defaultForm: FormState = {
  title: "雾都归档人",
  genre: "悬疑 · 都市",
  target_word_count: 300_000,
  target_chapter_count: 48,
  premise: "失忆档案修复师在雾都地下库房中发现自己被抹除的家族案卷。",
  style: "冷峻克制，细节密集",
};

export function CreateProjectPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [activeStep, setActiveStep] = useState(0);
  const [form, setForm] = useState<FormState>(defaultForm);

  const { data: quotas } = useQuery({
    queryKey: useScopedKey("quotas"),
    queryFn: () => quotaApi.list(),
  });
  const wordQuota = quotas?.find((q) => q.quota_key === "monthly_generated_words");

  const mutation = useMutation({
    mutationFn: () => projectsApi.create(form),
    onSuccess: (project) => {
      toast.success("项目已创建");
      queryClient.invalidateQueries({ queryKey: ["org"] });
      router.push(`/studio/projects/${project.id}`);
    },
    onError: (error: unknown) => {
      const msg = error instanceof ApiError ? error.message : "创建失败";
      toast.error(msg);
    },
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-black text-slate-950">新建小说项目</h1>
        <p className="mt-1 text-slate-500">4 步向导：收集设定、预估额度、创建后生成故事圣经。</p>
      </div>
      <div className="grid gap-6 xl:grid-cols-[0.72fr_1.28fr]">
        <Card>
          <CardHeader>
            <CardTitle>创建向导</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {steps.map((step, index) => (
              <button
                key={step}
                type="button"
                onClick={() => setActiveStep(index)}
                className={`flex w-full items-center gap-3 rounded-2xl border p-4 text-left transition ${
                  activeStep === index
                    ? "border-indigo-300 bg-indigo-50"
                    : "border-slate-200 hover:bg-slate-50"
                }`}
              >
                <div
                  className={`grid size-9 place-items-center rounded-full text-sm font-bold ${
                    activeStep >= index ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-500"
                  }`}
                >
                  {activeStep > index ? <CheckCircle2 className="size-5" /> : index + 1}
                </div>
                <div>
                  <p className="font-bold text-slate-950">{step}</p>
                  <p className="text-xs text-slate-500">
                    {index === 0
                      ? "标题、创意、目标字数"
                      : index === 1
                      ? "类型、文风、目标读者"
                      : index === 2
                      ? "自动生成预览与禁忌内容"
                      : "套餐、权益、额度检查"}
                  </p>
                </div>
              </button>
            ))}
            <div className="rounded-2xl bg-slate-50 p-4">
              <div className="mb-2 flex items-center gap-2 font-bold text-slate-950">
                <Gauge className="size-5 text-indigo-600" /> 套餐和额度检查
              </div>
              {wordQuota ? (
                <QuotaProgress
                  used={wordQuota.used_value}
                  reserved={wordQuota.reserved_value}
                  limit={wordQuota.limit_value}
                />
              ) : (
                <p className="text-sm text-slate-500">加载额度中…</p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>项目表单</CardTitle>
            <Badge tone="violet">长篇生产</Badge>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-4 md:grid-cols-2">
              <Field
                label="小说标题"
                value={form.title}
                onChange={(v) => setForm({ ...form, title: v })}
              />
              <Field
                label="小说类型"
                value={form.genre}
                onChange={(v) => setForm({ ...form, genre: v })}
              />
              <Field
                label="目标字数"
                type="number"
                value={String(form.target_word_count)}
                onChange={(v) =>
                  setForm({ ...form, target_word_count: Number(v) || 0 })
                }
              />
              <Field
                label="目标章节数"
                type="number"
                value={String(form.target_chapter_count)}
                onChange={(v) =>
                  setForm({ ...form, target_chapter_count: Number(v) || 0 })
                }
              />
            </div>
            <label className="block text-sm font-bold text-slate-700">
              一句话创意
              <textarea
                className="mt-2 min-h-24 w-full rounded-2xl border border-slate-200 p-4 outline-none focus:border-indigo-500"
                value={form.premise}
                onChange={(e) => setForm({ ...form, premise: e.target.value })}
              />
            </label>
            <label className="block text-sm font-bold text-slate-700">
              文风
              <textarea
                className="mt-2 min-h-24 w-full rounded-2xl border border-slate-200 p-4 outline-none focus:border-indigo-500"
                value={form.style}
                onChange={(e) => setForm({ ...form, style: e.target.value })}
              />
            </label>
            <div className="grid gap-4 md:grid-cols-2">
              <PreviewCard
                icon={Lightbulb}
                title="创建后自动生成预览"
                text="故事圣经、核心冲突、人物初始关系与世界规则。"
              />
              <PreviewCard
                icon={Wand2}
                title="预计额度"
                text={`预留 ${form.target_word_count.toLocaleString()} 字；完成后按实际输出结算。`}
              />
            </div>
            <div className="flex flex-wrap justify-end gap-3">
              <Button variant="ghost" onClick={() => router.push("/studio/projects")}>
                取消
              </Button>
              <Button
                onClick={() => mutation.mutate()}
                disabled={mutation.isPending || !form.title.trim()}
              >
                {mutation.isPending ? "创建中..." : "创建项目"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <label className="block text-sm font-bold text-slate-700">
      {label}
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-4 outline-none focus:border-indigo-500"
      />
    </label>
  );
}

function PreviewCard({
  icon: Icon,
  title,
  text,
}: {
  icon: typeof FileText;
  title: string;
  text: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <Icon className="size-5 text-indigo-600" />
      <p className="mt-2 font-bold text-slate-950">{title}</p>
      <p className="mt-1 text-sm text-slate-500">{text}</p>
    </div>
  );
}
