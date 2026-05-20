"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, RefreshCw, TimerReset, XCircle } from "lucide-react";
import { toast } from "sonner";

import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { ProgressBar } from "@/components/ui/progress";
import { ProjectHeader } from "@/components/screens/project/project-frame";
import { jobsApi } from "@/lib/api";
import { ApiError } from "@/lib/http";
import { useScopedKey } from "@/lib/use-scoped-key";

import { StatJob } from "./stat-job";

// =========== 任务 ===========
export function JobsPage({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const { data: allJobs = [] } = useQuery({
    queryKey: useScopedKey("jobs"),
    queryFn: () => jobsApi.list(),
  });
  const rows = allJobs.filter((j) => j.project_id === projectId);

  const cancel = useMutation({
    mutationFn: (id: string) => jobsApi.cancel(id),
    onSuccess: () => {
      toast.success("已取消");
      queryClient.invalidateQueries({ queryKey: ["org"] });
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "取消失败"),
  });

  const retry = useMutation({
    mutationFn: (id: string) => jobsApi.retry(id),
    onSuccess: (newJob) => {
      toast.success(`已重新提交任务（${newJob.job_type}）`);
      queryClient.invalidateQueries({ queryKey: ["org"] });
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "重试失败"),
  });

  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <div className="grid gap-4 lg:grid-cols-4">
        <StatJob
          label="队列中"
          value={rows.filter((j) => j.status === "queued").length}
          icon={TimerReset}
        />
        <StatJob
          label="运行中"
          value={rows.filter((j) => j.status === "running").length}
          icon={RefreshCw}
        />
        <StatJob
          label="已失败"
          value={rows.filter((j) => j.status === "failed").length}
          icon={XCircle}
        />
        <StatJob
          label="已完成"
          value={rows.filter((j) => j.status === "succeeded").length}
          icon={CheckCircle2}
        />
      </div>
      <Card>
        <CardHeader>
          <CardTitle>任务队列</CardTitle>
        </CardHeader>
        <CardContent>
          {rows.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">该项目暂无生成任务。</p>
          ) : (
            <DataTable
              rows={rows}
              columns={[
                {
                  key: "title",
                  header: "任务",
                  render: (row) => (
                    <div>
                      <p className="font-bold text-slate-950">{row.job_type}</p>
                      <p className="text-xs text-slate-500">{row.workflow_id ?? "—"}</p>
                    </div>
                  ),
                },
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
                    <ProgressBar
                      value={(row.consumed_quota / Math.max(row.reserved_quota, 1)) * 100}
                    />
                  ),
                },
                {
                  key: "actions",
                  header: "操作",
                  render: (row) => {
                    if (row.status === "queued" || row.status === "running") {
                      return (
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() => cancel.mutate(row.id)}
                          disabled={cancel.isPending}
                        >
                          取消
                        </Button>
                      );
                    }
                    if (row.status === "failed" || row.status === "cancelled") {
                      return (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => retry.mutate(row.id)}
                          disabled={retry.isPending}
                        >
                          <RefreshCw className="size-4" /> 重试
                        </Button>
                      );
                    }
                    return null;
                  },
                },
              ]}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
