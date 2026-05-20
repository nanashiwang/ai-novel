"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { AdminTitle } from "@/components/ui/admin-title";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { adminApi, type AdminUser, type AdminUserUpdate } from "@/lib/api";
import { isSuperAdmin } from "@/lib/permissions";

import { UserDetailDrawer } from "./user-detail-drawer";

export function AdminUsersPage() {
  const queryClient = useQueryClient();
  const { user: currentUser } = useAuth();
  const isSuper = isSuperAdmin(currentUser);
  const { data = [], isPending } = useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => adminApi.users() as Promise<AdminUser[]>,
  });
  const [detailUserId, setDetailUserId] = useState<string | null>(null);

  const updateMutation = useMutation({
    mutationFn: ({ userId, payload }: { userId: string; payload: AdminUserUpdate }) =>
      adminApi.updateUser(userId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "audit-logs"] });
      if (detailUserId) {
        queryClient.invalidateQueries({ queryKey: ["admin", "user", detailUserId] });
      }
      toast.success("已保存");
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : "保存失败"),
  });
  const resetPwdMutation = useMutation({
    mutationFn: (userId: string) => adminApi.resetUserPassword(userId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["admin", "audit-logs"] });
      window.prompt(
        "已重置密码。请复制临时密码并通过安全渠道告知用户：",
        data.temp_password,
      );
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : "重置失败"),
  });

  function toggleStatus(row: AdminUser) {
    if (row.id === currentUser?.id) {
      toast.error("不能禁用自己");
      return;
    }
    const nextStatus = row.status === "active" ? "disabled" : "active";
    if (!window.confirm(`确认把 ${row.email} 设为 ${nextStatus}？`)) return;
    updateMutation.mutate({ userId: row.id, payload: { status: nextStatus } });
  }

  function changeRole(row: AdminUser, nextRole: string) {
    if (nextRole === row.platform_role) return;
    if (row.id === currentUser?.id) {
      toast.error("不能修改自己的角色");
      return;
    }
    if ((nextRole === "admin" || nextRole === "super_admin") && !isSuper) {
      toast.error("仅 super_admin 可提升角色");
      return;
    }
    if (!window.confirm(`确认把 ${row.email} 的角色改为 ${nextRole}？`)) return;
    updateMutation.mutate({ userId: row.id, payload: { platform_role: nextRole } });
  }

  function resetPwd(row: AdminUser) {
    if (!window.confirm(`确认重置 ${row.email} 的密码？旧密码将立即失效。`)) return;
    resetPwdMutation.mutate(row.id);
  }

  return (
    <div className="space-y-6">
      <AdminTitle title="用户管理" desc="平台用户、角色、状态。可禁用、改角色、重置密码。" />
      {isPending ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">加载中…</CardContent>
        </Card>
      ) : (
        <DataTable
          rows={data}
          columns={[
            {
              key: "name",
              header: "用户",
              render: (row) => (
                <div>
                  <button
                    type="button"
                    onClick={() => setDetailUserId(row.id)}
                    className="text-left font-bold text-slate-950 hover:text-indigo-600"
                  >
                    {row.display_name}
                  </button>
                  <p className="text-xs text-slate-500">{row.email}</p>
                </div>
              ),
            },
            {
              key: "role",
              header: "角色",
              render: (row) => (
                <select
                  disabled={row.id === currentUser?.id}
                  value={row.platform_role}
                  onChange={(e) => changeRole(row, e.target.value)}
                  className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs disabled:bg-slate-100"
                >
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                  <option value="super_admin">super_admin</option>
                </select>
              ),
            },
            {
              key: "status",
              header: "状态",
              render: (row) => (
                <StatusBadge status={row.status === "active" ? "succeeded" : "failed"} />
              ),
            },
            {
              key: "actions",
              header: "操作",
              render: (row) => (
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={row.id === currentUser?.id || updateMutation.isPending}
                    onClick={() => toggleStatus(row)}
                  >
                    {row.status === "active" ? "禁用" : "启用"}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={resetPwdMutation.isPending}
                    onClick={() => resetPwd(row)}
                  >
                    <KeyRound className="size-3.5" /> 重置密码
                  </Button>
                </div>
              ),
            },
            { key: "id", header: "user_id", render: (row) => row.id },
          ]}
        />
      )}
      {detailUserId ? (
        <UserDetailDrawer userId={detailUserId} onClose={() => setDetailUserId(null)} />
      ) : null}
    </div>
  );
}
