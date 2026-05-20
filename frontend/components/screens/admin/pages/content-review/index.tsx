"use client";

import { useQuery } from "@tanstack/react-query";

import { AdminTitle } from "@/components/ui/admin-title";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import type { AdminContentReview } from "@/components/screens/admin/shared/types";
import { adminApi } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export function AdminContentReviewPage() {
  const { data = [] } = useQuery({
    queryKey: ["admin", "content-reviews"],
    queryFn: () => adminApi.contentReviews() as Promise<AdminContentReview[]>,
  });
  return (
    <div className="space-y-6">
      <AdminTitle title="内容审核 / 风控" desc="待审核内容、风险等级、处理动作。" />
      {data.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">暂无需要审核的内容。</CardContent>
        </Card>
      ) : (
        <DataTable
          rows={data}
          columns={[
            {
              key: "title",
              header: "内容",
              render: (row) => (
                <div>
                  <p className="font-bold text-slate-950">{row.description.slice(0, 60)}</p>
                  <p className="text-xs text-slate-500">
                    {row.organization_id} / {row.project_id}
                  </p>
                </div>
              ),
            },
            { key: "type", header: "类型", render: (row) => row.issue_type },
            {
              key: "severity",
              header: "风险",
              render: (row) => (
                <Badge
                  tone={
                    row.severity === "high"
                      ? "rose"
                      : row.severity === "medium"
                      ? "amber"
                      : "green"
                  }
                >
                  {row.severity}
                </Badge>
              ),
            },
            { key: "status", header: "状态", render: (row) => row.status },
            { key: "time", header: "时间", render: (row) => formatDateTime(row.created_at) },
          ]}
        />
      )}
    </div>
  );
}
