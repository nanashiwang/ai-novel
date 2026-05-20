"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Link2, LockKeyhole, Save, Server, Sparkles } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { AdminTitle } from "@/components/ui/admin-title";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  adminApi,
  type ModelGatewaySettingsUpdate,
  type ModelGatewayTestPayload,
} from "@/lib/api";
import { isSuperAdmin } from "@/lib/permissions";

import { ProviderFields } from "./provider-fields";
import { SegmentButton } from "./segment-button";
import { SettingStatusCard } from "./setting-status-card";

export function AdminSettingsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const editable = isSuperAdmin(user);
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "settings", "model-gateway"],
    queryFn: adminApi.modelGatewaySettings,
  });
  const [draft, setDraft] = useState<Partial<ModelGatewaySettingsUpdate>>({});
  const form: ModelGatewaySettingsUpdate = {
    provider: draft.provider ?? data?.provider ?? "openai",
    default_model: draft.default_model ?? data?.default_model ?? "gpt-5.5",
    openai_base_url:
      draft.openai_base_url ?? data?.openai_base_url ?? "https://api.openai.com/v1",
    openai_api_key: draft.openai_api_key ?? "",
    anthropic_base_url:
      draft.anthropic_base_url ?? data?.anthropic_base_url ?? "https://api.anthropic.com/v1",
    anthropic_api_key: draft.anthropic_api_key ?? "",
  };

  const saveMutation = useMutation({
    mutationFn: (payload: ModelGatewaySettingsUpdate) =>
      adminApi.updateModelGatewaySettings(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "settings", "model-gateway"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "audit-logs"] });
      setDraft({});
      toast.success("模型配置已保存");
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "保存失败");
    },
  });

  const testMutation = useMutation({
    mutationFn: () => {
      // 只传当前 form 草稿里"非空"的字段。后端会把缺失字段回落到 db 里
      // 已存的值，从而支持"我只改 base_url，用现有 Key 测试"等场景。
      const payload: ModelGatewayTestPayload = {
        provider: form.provider,
        default_model: form.default_model.trim() || undefined,
        openai_base_url: form.openai_base_url.trim() || undefined,
        openai_api_key: form.openai_api_key?.trim() || undefined,
        anthropic_base_url: form.anthropic_base_url.trim() || undefined,
        anthropic_api_key: form.anthropic_api_key?.trim() || undefined,
      };
      return adminApi.testModelGateway(payload);
    },
    onSuccess: (result) => {
      if (result.ok) {
        toast.success(
          `连接成功（${result.latency_ms} ms）样例：${result.sample || "OK"}`,
        );
      } else {
        const friendly =
          result.error === "missing_api_key"
            ? "缺少 API Key"
            : result.error === "timeout_15s"
              ? "请求超时（>15s）"
              : result.error || "未知错误";
        toast.error(`连接失败：${friendly}`);
      }
    },
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : "测试请求失败"),
  });

  const selectedKeyConfigured =
    form.provider === "anthropic"
      ? data?.anthropic_api_key_configured
      : data?.openai_api_key_configured;
  const typedSelectedKey =
    form.provider === "anthropic" ? form.anthropic_api_key : form.openai_api_key;
  const canSave =
    editable &&
    form.default_model.trim() &&
    form.openai_base_url.trim() &&
    form.anthropic_base_url.trim() &&
    (selectedKeyConfigured || typedSelectedKey?.trim());

  function updateField<K extends keyof ModelGatewaySettingsUpdate>(
    key: K,
    value: ModelGatewaySettingsUpdate[K],
  ) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function save() {
    saveMutation.mutate({
      ...form,
      default_model: form.default_model.trim(),
      openai_base_url: form.openai_base_url.trim(),
      openai_api_key: form.openai_api_key?.trim() || null,
      anthropic_base_url: form.anthropic_base_url.trim(),
      anthropic_api_key: form.anthropic_api_key?.trim() || null,
    });
  }

  return (
    <div className="space-y-6">
      <AdminTitle title="系统设置" desc="配置模型服务地址、密钥和默认模型。" />
      {!editable ? (
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="flex items-center gap-3 text-amber-800">
            <LockKeyhole className="size-5" /> 当前角色只能查看。
          </CardContent>
        </Card>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-3">
        <SettingStatusCard
          icon={Server}
          label="运行模式"
          value="真实模型"
          tone="green"
        />
        <SettingStatusCard
          icon={Link2}
          label="当前地址"
          value={data?.active_base_url ?? "-"}
          tone={data?.ready ? "green" : "rose"}
        />
        <SettingStatusCard
          icon={KeyRound}
          label="密钥状态"
          value={selectedKeyConfigured ? "已配置" : "未配置"}
          tone={selectedKeyConfigured ? "green" : "rose"}
        />
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4">
          <div>
            <CardTitle>模型网关</CardTitle>
            <p className="mt-1 text-sm text-slate-500">
              这里保存后，后端生成任务会使用新的 URL 和 Key。
            </p>
          </div>
          <Badge tone={data?.ready ? "green" : "amber"}>
            {isLoading ? "加载中" : data?.ready ? "可用" : "待配置"}
          </Badge>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-3">
            <SegmentButton
              active
              disabled={!editable}
              title="真实模型生产模式"
              desc="所有生成链路直接调用下方 URL 和 Key"
              onClick={() => undefined}
            />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="block text-sm font-bold text-slate-700">
              服务商
              <select
                disabled={!editable}
                value={form.provider}
                onChange={(e) =>
                  updateField(
                    "provider",
                    e.target.value === "anthropic" ? "anthropic" : "openai",
                  )
                }
                className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-4 disabled:bg-slate-100"
              >
                <option value="openai">OpenAI / 兼容接口</option>
                <option value="anthropic">Anthropic</option>
              </select>
            </label>
            <label className="block text-sm font-bold text-slate-700">
              默认模型
              <input
                disabled={!editable}
                value={form.default_model}
                onChange={(e) => updateField("default_model", e.target.value)}
                placeholder="gpt-5.5"
                className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-4 disabled:bg-slate-100"
              />
            </label>
          </div>

          <ProviderFields
            title="OpenAI / 兼容接口"
            active={form.provider === "openai"}
            configured={Boolean(data?.openai_api_key_configured)}
            baseUrl={form.openai_base_url}
            apiKey={form.openai_api_key ?? ""}
            disabled={!editable}
            onBaseUrlChange={(value) => updateField("openai_base_url", value)}
            onApiKeyChange={(value) => updateField("openai_api_key", value)}
            baseUrlPlaceholder="https://api.openai.com/v1"
            keyPlaceholder={
              data?.openai_api_key_configured ? "留空表示保留已有 Key" : "sk-..."
            }
          />

          <ProviderFields
            title="Anthropic"
            active={form.provider === "anthropic"}
            configured={Boolean(data?.anthropic_api_key_configured)}
            baseUrl={form.anthropic_base_url}
            apiKey={form.anthropic_api_key ?? ""}
            disabled={!editable}
            onBaseUrlChange={(value) => updateField("anthropic_base_url", value)}
            onApiKeyChange={(value) => updateField("anthropic_api_key", value)}
            baseUrlPlaceholder="https://api.anthropic.com/v1"
            keyPlaceholder={
              data?.anthropic_api_key_configured ? "留空表示保留已有 Key" : "sk-ant-..."
            }
          />

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-5">
            <p className="text-sm text-slate-500">
              {!canSave
                ? "真实模型模式需要当前服务商的 Key。"
                : "Key 不会在页面回显。可先用「测试连接」验证再保存。"}
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                disabled={!editable || testMutation.isPending}
                onClick={() => testMutation.mutate()}
              >
                <Sparkles className="size-4" />
                {testMutation.isPending ? "测试中…" : "测试连接"}
              </Button>
              <Button disabled={!canSave || saveMutation.isPending} onClick={save}>
                <Save className="size-4" />
                {saveMutation.isPending ? "保存中" : "保存配置"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
