"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { AdminTitle } from "@/components/ui/admin-title";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { QuotaProgress } from "@/components/ui/progress";
import { adminApi } from "@/lib/api";
import { isSuperAdmin } from "@/lib/permissions";

export function AdminQuotasPage() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const editable = isSuperAdmin(user);
  const [filter, setFilter] = useState<{ organization_id: string; quota_key: string }>({
    organization_id: "",
    quota_key: "",
  });
  const queryFilter = {
    organization_id: filter.organization_id || undefined,
    quota_key: filter.quota_key || undefined,
  };
  const { data = [], isLoading } = useQuery({
    queryKey: ["admin", "quotas", queryFilter],
    queryFn: () => adminApi.quotaBalances(queryFilter),
  });
  const { data: quotaKeyOptions = [] } = useQuery({
    queryKey: ["admin", "quota-keys"],
    queryFn: adminApi.quotaKeys,
  });

  const adjustMutation = useMutation({
    mutationFn: ({
      orgId,
      payload,
    }: {
      orgId: string;
      payload: { quota_key: string; delta: number; reason: string };
    }) => adminApi.adjustOrganizationQuota(orgId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "quotas"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "audit-logs"] });
      toast.success("已写入 audit_logs");
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : "调整失败"),
  });

  function adjust(quota: { organization_id: string; quota_key: string }, sign: 1 | -1) {
    const raw = window.prompt(
      `输入要${sign > 0 ? "增加" : "扣减"}的额度（${quota.quota_key}）：`,
      "1000",
    );
    if (!raw) return;
    const amount = Number(raw);
    if (!Number.isFinite(amount) || amount <= 0) {
      toast.error("请输入正整数");
      return;
    }
    const reason = window.prompt("调整原因（写入 audit_log）", "运营补偿") || "";
    adjustMutation.mutate({
      orgId: quota.organization_id,
      payload: { quota_key: quota.quota_key, delta: sign * amount, reason },
    });
  }

  return (
    <div className="space-y-6">
      <AdminTitle title="额度管理" desc="组织额度 / 预留 / 已用。手动调整自动写入 audit_logs。" />
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center gap-3">
          <CardTitle>quota_balances</CardTitle>
          <input
            type="text"
            placeholder="organization_id 过滤"
            value={filter.organization_id}
            onChange={(e) =>
              setFilter((f) => ({ ...f, organization_id: e.target.value.trim() }))
            }
            className="h-9 w-64 rounded-lg border border-slate-200 px-3 text-sm"
          />
          <select
            value={filter.quota_key}
            onChange={(e) => setFilter((f) => ({ ...f, quota_key: e.target.value }))}
            className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm"
          >
            <option value="">全部额度类型</option>
            {quotaKeyOptions.map((opt) => (
              <option key={opt.feature_key} value={opt.feature_key}>
                {opt.feature_key}
              </option>
            ))}
          </select>
          {!editable ? (
            <Badge tone="amber">仅 super_admin 可调整</Badge>
          ) : null}
        </CardHeader>
      </Card>
      {isLoading ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">加载中…</CardContent>
        </Card>
      ) : data.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">
            暂无符合条件的额度记录。
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((quota) => (
            <Card key={quota.id}>
              <CardContent>
                <div className="mb-3 flex items-center justify-between">
                  <p className="font-bold text-slate-950">{quota.quota_key}</p>
                  <Badge tone="blue">{quota.organization_id.slice(0, 14)}</Badge>
                </div>
                <QuotaProgress
                  used={quota.used_value}
                  reserved={quota.reserved_value}
                  limit={quota.limit_value}
                />
                <div className="mt-3 flex justify-end gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={!editable || adjustMutation.isPending}
                    onClick={() => adjust(quota, 1)}
                  >
                    + 加额
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={!editable || adjustMutation.isPending}
                    onClick={() => adjust(quota, -1)}
                  >
                    − 扣减
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
