"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { AdminTitle } from "@/components/ui/admin-title";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import type { AdminModelCall } from "@/components/screens/admin/shared/types";
import { adminApi } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export function AdminModelCallsPage() {
  const [filter, setFilter] = useState<{ project_id: string; job_id: string }>(
    { project_id: "", job_id: "" },
  );
  const queryFilter = {
    project_id: filter.project_id || undefined,
    job_id: filter.job_id || undefined,
  };
  const { data = [], refetch } = useQuery({
    queryKey: ["admin", "model-calls", queryFilter],
    queryFn: () => adminApi.modelCalls(queryFilter) as Promise<AdminModelCall[]>,
  });
  return (
    <div className="space-y-6">
      <AdminTitle title="模型调用日志" desc="ModelGateway 统一记录 task_type、model、token、latency、status；可按 project / job drill-down。" />
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center gap-3">
          <CardTitle>model_calls</CardTitle>
          <input
            type="text"
            placeholder="project_id"
            value={filter.project_id}
            onChange={(e) => setFilter((f) => ({ ...f, project_id: e.target.value }))}
            className="h-9 w-56 rounded-lg border border-slate-200 px-3 text-sm"
          />
          <input
            type="text"
            placeholder="job_id"
            value={filter.job_id}
            onChange={(e) => setFilter((f) => ({ ...f, job_id: e.target.value }))}
            className="h-9 w-56 rounded-lg border border-slate-200 px-3 text-sm"
          />
          <Button size="sm" variant="ghost" onClick={() => refetch()}>
            刷新
          </Button>
        </CardHeader>
        <CardContent>
          {data.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">无匹配记录。</p>
          ) : (
            <DataTable
              rows={data}
              columns={[
                { key: "task", header: "task_type", render: (row) => row.task_type },
                { key: "model", header: "model", render: (row) => row.model },
                {
                  key: "tokens",
                  header: "tokens",
                  render: (row) => `in ${row.input_tokens} / out ${row.output_tokens}`,
                },
                { key: "latency", header: "latency", render: (row) => `${row.latency_ms}ms` },
                {
                  key: "status",
                  header: "status",
                  render: (row) => (
                    <StatusBadge status={row.status === "success" ? "succeeded" : "failed"} />
                  ),
                },
                {
                  key: "job",
                  header: "job_id",
                  render: (row) =>
                    row.job_id ? (
                      <button
                        type="button"
                        className="font-mono text-xs text-indigo-600 hover:underline"
                        onClick={() =>
                          setFilter((f) => ({ ...f, job_id: row.job_id ?? "" }))
                        }
                        title="点击 drill-down 到该 job"
                      >
                        {row.job_id.slice(0, 16)}…
                      </button>
                    ) : (
                      <span className="text-slate-400">—</span>
                    ),
                },
                { key: "time", header: "时间", render: (row) => formatDateTime(row.created_at) },
              ]}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
