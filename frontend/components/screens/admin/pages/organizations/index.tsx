"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LockKeyhole } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { AdminTitle } from "@/components/ui/admin-title";
import { PlanBadge, StatusBadge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import type { AdminOrg } from "@/components/screens/admin/shared/types";
import { adminApi } from "@/lib/api";
import { isSuperAdmin } from "@/lib/permissions";

export function AdminOrganizationsPage() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const editable = isSuperAdmin(user);
  const { data = [] } = useQuery({
    queryKey: ["admin", "organizations"],
    queryFn: () => adminApi.organizations() as Promise<AdminOrg[]>,
  });
  const { data: plans = [] } = useQuery({
    queryKey: ["admin", "plans"],
    queryFn: adminApi.plans,
  });
  // 仅 active 套餐可用于切换；archived 仍允许保留历史绑定
  const activePlanCodes = plans
    .filter((p) => p.status === "active")
    .map((p) => p.code);

  const switchPlanMutation = useMutation({
    mutationFn: ({ orgId, planCode }: { orgId: string; planCode: string }) =>
      adminApi.updateOrganization(orgId, {
        plan_code: planCode,
        reason: "admin 手动调整",
      }),
    onSuccess: () => {
      toast.success("已切换套餐，额度按新套餐自动同步");
      queryClient.invalidateQueries({ queryKey: ["admin", "organizations"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "plans"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "quotas"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "audit-logs"] });
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "切换套餐失败");
    },
  });

  function changePlan(row: AdminOrg, nextPlan: string) {
    if (nextPlan === row.plan_code) return;
    const confirmed = window.confirm(
      `确认把组织 ${row.name} 从 ${row.plan_code} 切换为 ${nextPlan}？\n` +
        `已用额度（used）保留，额度上限会按新套餐重置。`,
    );
    if (!confirmed) return;
    switchPlanMutation.mutate({ orgId: row.id, planCode: nextPlan });
  }

  return (
    <div className="space-y-6">
      <AdminTitle title="组织管理" desc="组织状态、套餐、成员入口。" />
      {!editable ? (
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="flex items-center gap-3 text-amber-800">
            <LockKeyhole className="size-5" /> 仅 super_admin 可切换套餐。
          </CardContent>
        </Card>
      ) : null}
      {data.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">暂无组织。</CardContent>
        </Card>
      ) : (
        <DataTable
          rows={data}
          columns={[
            {
              key: "name",
              header: "组织",
              render: (row) => <span className="font-bold text-slate-950">{row.name}</span>,
            },
            { key: "owner", header: "owner_user_id", render: (row) => row.owner_user_id },
            {
              key: "plan",
              header: "Plan",
              render: (row) => (
                <div className="flex items-center gap-2">
                  <PlanBadge plan={row.plan_code as never} />
                  <select
                    disabled={!editable || switchPlanMutation.isPending}
                    value={row.plan_code}
                    onChange={(e) => changePlan(row, e.target.value)}
                    className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs disabled:bg-slate-100"
                  >
                    {!activePlanCodes.includes(row.plan_code) ? (
                      <option value={row.plan_code}>{row.plan_code}（当前）</option>
                    ) : null}
                    {activePlanCodes.map((code) => (
                      <option key={code} value={code}>
                        {code}
                      </option>
                    ))}
                  </select>
                </div>
              ),
            },
            {
              key: "status",
              header: "状态",
              render: (row) => (
                <StatusBadge
                  status={row.status === "active" ? "succeeded" : row.status === "trialing" ? "queued" : "failed"}
                />
              ),
            },
          ]}
        />
      )}
    </div>
  );
}
