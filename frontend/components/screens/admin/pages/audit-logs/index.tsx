"use client";

import { useQuery } from "@tanstack/react-query";

import { AdminTitle } from "@/components/ui/admin-title";
import { Card, CardContent } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import type { AdminAuditLog } from "@/components/screens/admin/shared/types";
import { adminApi } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export function AdminAuditLogsPage() {
  const { data = [] } = useQuery({
    queryKey: ["admin", "audit-logs"],
    queryFn: () => adminApi.auditLogs() as Promise<AdminAuditLog[]>,
  });
  return (
    <div className="space-y-6">
      <AdminTitle title="审计日志" desc="所有管理员破坏性操作必须记录。" />
      {data.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">暂无审计日志。</CardContent>
        </Card>
      ) : (
        <DataTable
          rows={data}
          columns={[
            {
              key: "actor",
              header: "actor",
              render: (row) => <span className="font-bold text-slate-950">{row.actor_user_id}</span>,
            },
            { key: "action", header: "action", render: (row) => row.action },
            { key: "target", header: "target", render: (row) => `${row.target_type}/${row.target_id}` },
            { key: "org", header: "组织", render: (row) => row.organization_id },
            { key: "time", header: "时间", render: (row) => formatDateTime(row.created_at) },
          ]}
        />
      )}
    </div>
  );
}
