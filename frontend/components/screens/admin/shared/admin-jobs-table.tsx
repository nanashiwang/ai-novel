"use client";

import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { ProgressBar } from "@/components/ui/progress";
import type { GenerationJob } from "@/lib/api";

export type AdminJobsTableProps = {
  rows: GenerationJob[];
  onCancel?: (id: string) => void;
};

export function AdminJobsTable({ rows, onCancel }: AdminJobsTableProps) {
  return (
    <DataTable
      rows={rows}
      columns={[
        {
          key: "title",
          header: "任务",
          render: (row) => (
            <div>
              <p className="font-bold text-slate-950">{row.job_type}</p>
              <p className="text-xs text-slate-500">{row.workflow_id ?? "未启动 workflow"}</p>
            </div>
          ),
        },
        { key: "org", header: "organization_id", render: (row) => row.organization_id },
        { key: "type", header: "task_type", render: (row) => row.job_type },
        {
          key: "status",
          header: "状态",
          render: (row) => <StatusBadge status={row.status as never} />,
        },
        {
          key: "quota",
          header: "额度",
          render: (row) => `${row.consumed_quota}/${row.reserved_quota}`,
        },
        {
          key: "progress",
          header: "进度",
          render: (row) => (
            <ProgressBar value={(row.consumed_quota / Math.max(row.reserved_quota, 1)) * 100} />
          ),
        },
        {
          key: "action",
          header: "强制操作",
          render: (row) =>
            onCancel ? (
              <Button size="sm" variant="danger" onClick={() => onCancel(row.id)}>
                取消
              </Button>
            ) : null,
        },
      ]}
    />
  );
}
