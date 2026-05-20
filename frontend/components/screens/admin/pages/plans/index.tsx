"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, LockKeyhole, Plus, Save, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { AdminTitle } from "@/components/ui/admin-title";
import { Badge, PlanBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { adminApi, type AdminPlanFeature, type AdminPlanUpsert } from "@/lib/api";
import { isSuperAdmin } from "@/lib/permissions";

import { buildPlanForm } from "./build-plan-form";

export function AdminPlansPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const editable = isSuperAdmin(user);
  const { data = [], isLoading } = useQuery({
    queryKey: ["admin", "plans"],
    queryFn: adminApi.plans,
  });
  const { data: quotaKeyOptions = [] } = useQuery({
    queryKey: ["admin", "quota-keys"],
    queryFn: adminApi.quotaKeys,
  });
  const [selectedId, setSelectedId] = useState<string | "new">("new");
  const selectedPlan =
    selectedId === "new" ? undefined : data.find((plan) => plan.id === selectedId);
  const [draft, setDraft] = useState<Partial<AdminPlanUpsert>>({});
  const form = buildPlanForm(selectedPlan, draft);

  const saveMutation = useMutation({
    mutationFn: (payload: AdminPlanUpsert) =>
      selectedPlan
        ? adminApi.updatePlan(selectedPlan.id, payload)
        : adminApi.createPlan(payload),
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ["admin", "plans"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "quota-keys"] });
      queryClient.invalidateQueries({ queryKey: ["billing", "plans"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "audit-logs"] });
      setSelectedId(saved.id);
      setDraft({});
      toast.success("套餐已保存");
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "保存失败");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (planId: string) => adminApi.deletePlan(planId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "plans"] });
      queryClient.invalidateQueries({ queryKey: ["billing", "plans"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "audit-logs"] });
      setSelectedId("new");
      setDraft({});
      toast.success("套餐已删除");
    },
    onError: (error) => {
      const msg = error instanceof Error ? error.message : "删除失败";
      // 后端返回 plan_in_use 时给更友好的提示
      toast.error(msg.includes("plan_in_use") ? "仍有组织使用此套餐，无法删除" : msg);
    },
  });

  function selectPlan(id: string | "new") {
    setSelectedId(id);
    setDraft({});
  }

  function updateField<K extends keyof AdminPlanUpsert>(key: K, value: AdminPlanUpsert[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function updateFeature(index: number, patch: Partial<AdminPlanFeature>) {
    const features = form.features.map((feature, featureIndex) =>
      featureIndex === index ? { ...feature, ...patch } : feature,
    );
    updateField("features", features);
  }

  function addFeature() {
    updateField("features", [
      ...form.features,
      {
        feature_key: quotaKeyOptions[0]?.feature_key ?? "monthly_generated_words",
        enabled: true,
        limit_value: 0,
        limit_unit: "words",
      },
    ]);
  }

  function removeFeature(index: number) {
    updateField(
      "features",
      form.features.filter((_, featureIndex) => featureIndex !== index),
    );
  }

  function deletePlan() {
    if (!selectedPlan) return;
    const orgCount = selectedPlan.organization_count ?? 0;
    if (orgCount > 0) {
      toast.error(`仍有 ${orgCount} 个组织在使用此套餐，请先把它们迁走再删除`);
      return;
    }
    if (!window.confirm(`确认删除套餐「${selectedPlan.name}」？此操作不可恢复。`)) return;
    deleteMutation.mutate(selectedPlan.id);
  }

  function savePlan() {
    const payload: AdminPlanUpsert = {
      ...form,
      code: form.code.trim(),
      name: form.name.trim(),
      description: form.description.trim(),
      currency: form.currency.trim() || "CNY",
      status: form.status.trim() || "active",
      price_monthly: Number(form.price_monthly) || 0,
      price_yearly: form.price_yearly === null ? null : Number(form.price_yearly) || 0,
      features: form.features
        .filter((feature) => feature.feature_key.trim())
        .map((feature) => ({
          feature_key: feature.feature_key.trim(),
          enabled: feature.enabled,
          limit_value:
            feature.limit_value === null || Number.isNaN(Number(feature.limit_value))
              ? null
              : Number(feature.limit_value),
          limit_unit: feature.limit_unit.trim() || "times",
        })),
    };
    saveMutation.mutate(payload);
  }

  const canSave = editable && form.code.trim() && form.name.trim();

  return (
    <div className="space-y-6">
      <AdminTitle title="套餐 / 权益管理" desc="自定义套餐、价格周期和周期内额度。" />
      {!editable ? (
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="flex items-center gap-3 text-amber-800">
            <LockKeyhole className="size-5" /> 当前角色只能查看。
          </CardContent>
        </Card>
      ) : null}
      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>套餐列表</CardTitle>
            <Button size="sm" variant="secondary" disabled={!editable} onClick={() => selectPlan("new")}>
              <Plus className="size-4" /> 新增
            </Button>
          </CardHeader>
          <CardContent className="space-y-2">
            {isLoading ? (
              <p className="py-8 text-center text-sm text-slate-500">加载中…</p>
            ) : data.length === 0 ? (
              <p className="py-8 text-center text-sm text-slate-500">暂无套餐。</p>
            ) : (
              data.map((plan) => (
                <button
                  key={plan.id}
                  type="button"
                  onClick={() => selectPlan(plan.id)}
                  className={`w-full rounded-xl border p-4 text-left transition ${
                    selectedId === plan.id
                      ? "border-indigo-500 bg-indigo-50"
                      : "border-slate-200 bg-white hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <PlanBadge plan={plan.code as never} />
                    <StatusBadge status={plan.status === "active" ? "succeeded" : "queued"} />
                  </div>
                  <p className="mt-3 font-black text-slate-950">{plan.name}</p>
                  <p className="mt-1 truncate text-sm text-slate-500">{plan.description || "-"}</p>
                  <p className="mt-2 text-sm font-semibold text-slate-700">
                    {plan.currency} {plan.price_monthly}/月
                    {plan.price_yearly !== null ? ` · ${plan.price_yearly}/年` : ""}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    <Building2 className="mr-1 inline size-3" />
                    使用组织：{plan.organization_count ?? 0}
                  </p>
                </button>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-4">
            <div>
              <CardTitle>{selectedPlan ? "编辑套餐" : "新增套餐"}</CardTitle>
              <p className="mt-1 text-sm text-slate-500">
                额度项会用于生成任务的周期限制。
              </p>
            </div>
            <div className="flex items-center gap-2">
              {selectedPlan ? (
                <Badge tone={(selectedPlan.organization_count ?? 0) > 0 ? "blue" : "amber"}>
                  绑定组织 {selectedPlan.organization_count ?? 0}
                </Badge>
              ) : null}
              <Badge tone={editable ? "green" : "amber"}>
                {editable ? "super_admin 可编辑" : "只读"}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2">
              <label className="block text-sm font-bold text-slate-700">
                套餐编码
                <input
                  disabled={!editable}
                  value={form.code}
                  onChange={(e) => updateField("code", e.target.value)}
                  placeholder="Pro"
                  className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-4 disabled:bg-slate-100"
                />
              </label>
              <label className="block text-sm font-bold text-slate-700">
                套餐名称
                <input
                  disabled={!editable}
                  value={form.name}
                  onChange={(e) => updateField("name", e.target.value)}
                  placeholder="Pro"
                  className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-4 disabled:bg-slate-100"
                />
              </label>
              <label className="block text-sm font-bold text-slate-700 md:col-span-2">
                描述
                <input
                  disabled={!editable}
                  value={form.description}
                  onChange={(e) => updateField("description", e.target.value)}
                  placeholder="长篇小说自动生产与审稿"
                  className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-4 disabled:bg-slate-100"
                />
              </label>
            </div>

            <div className="grid gap-4 md:grid-cols-4">
              <label className="block text-sm font-bold text-slate-700">
                月付价格
                <input
                  disabled={!editable}
                  value={form.price_monthly}
                  onChange={(e) => updateField("price_monthly", Number(e.target.value))}
                  type="number"
                  min="0"
                  className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-4 disabled:bg-slate-100"
                />
              </label>
              <label className="block text-sm font-bold text-slate-700">
                年付价格
                <input
                  disabled={!editable}
                  value={form.price_yearly ?? ""}
                  onChange={(e) =>
                    updateField(
                      "price_yearly",
                      e.target.value === "" ? null : Number(e.target.value),
                    )
                  }
                  type="number"
                  min="0"
                  placeholder="可留空"
                  className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-4 disabled:bg-slate-100"
                />
              </label>
              <label className="block text-sm font-bold text-slate-700">
                币种
                <input
                  disabled={!editable}
                  value={form.currency}
                  onChange={(e) => updateField("currency", e.target.value)}
                  className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-4 disabled:bg-slate-100"
                />
              </label>
              <label className="block text-sm font-bold text-slate-700">
                状态
                <select
                  disabled={!editable}
                  value={form.status}
                  onChange={(e) => updateField("status", e.target.value)}
                  className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-4 disabled:bg-slate-100"
                >
                  <option value="active">active</option>
                  <option value="draft">draft</option>
                  <option value="archived">archived</option>
                </select>
              </label>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-bold text-slate-950">周期内额度</p>
                  <p className="text-sm text-slate-500">
                    例如每月生成字数、审核次数、重写次数。
                  </p>
                </div>
                <Button size="sm" variant="secondary" disabled={!editable} onClick={addFeature}>
                  <Plus className="size-4" /> 添加额度
                </Button>
              </div>

              <div className="space-y-3">
                {form.features.map((feature, index) => (
                  <div
                    key={`${feature.feature_key}-${index}`}
                    className="grid gap-3 rounded-xl border border-slate-200 p-3 md:grid-cols-[1fr_140px_120px_90px_40px]"
                  >
                    <input
                      disabled={!editable}
                      value={feature.feature_key}
                      onChange={(e) => updateFeature(index, { feature_key: e.target.value })}
                      placeholder="monthly_generated_words"
                      list="admin-plan-quota-keys"
                      className="h-10 rounded-xl border border-slate-200 px-3 disabled:bg-slate-100"
                    />
                    <input
                      disabled={!editable}
                      value={feature.limit_value ?? ""}
                      onChange={(e) =>
                        updateFeature(index, {
                          limit_value: e.target.value === "" ? null : Number(e.target.value),
                        })
                      }
                      type="number"
                      min="0"
                      placeholder="额度"
                      className="h-10 rounded-xl border border-slate-200 px-3 disabled:bg-slate-100"
                    />
                    <input
                      disabled={!editable}
                      value={feature.limit_unit}
                      onChange={(e) => updateFeature(index, { limit_unit: e.target.value })}
                      placeholder="words"
                      className="h-10 rounded-xl border border-slate-200 px-3 disabled:bg-slate-100"
                    />
                    <label className="flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-3 text-sm font-semibold text-slate-700">
                      <input
                        disabled={!editable}
                        checked={feature.enabled}
                        onChange={(e) => updateFeature(index, { enabled: e.target.checked })}
                        type="checkbox"
                      />
                      启用
                    </label>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={!editable}
                      onClick={() => removeFeature(index)}
                      className="h-10 px-0"
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                ))}
                {form.features.length === 0 ? (
                  <p className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
                    暂无额度项。
                  </p>
                ) : null}
                {/* 全局 datalist：feature_key 自动补全。来源 GET /admin/quota-keys */}
                <datalist id="admin-plan-quota-keys">
                  {quotaKeyOptions.map((opt) => (
                    <option key={opt.feature_key} value={opt.feature_key}>
                      {opt.feature_key}
                    </option>
                  ))}
                </datalist>
              </div>
            </div>

            <div className="flex items-center justify-between border-t border-slate-100 pt-5">
              {selectedPlan ? (
                <Button
                  variant="ghost"
                  disabled={!editable || deleteMutation.isPending}
                  onClick={deletePlan}
                  className="text-red-600 hover:bg-red-50"
                >
                  <Trash2 className="size-4" />
                  {deleteMutation.isPending ? "删除中" : "删除套餐"}
                </Button>
              ) : (
                <span />
              )}
              <Button disabled={!canSave || saveMutation.isPending} onClick={savePlan}>
                <Save className="size-4" />
                {saveMutation.isPending ? "保存中" : "保存套餐"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
