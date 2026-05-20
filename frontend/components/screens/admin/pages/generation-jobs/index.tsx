"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { AdminTitle } from "@/components/ui/admin-title";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AdminJobsTable } from "@/components/screens/admin/shared/admin-jobs-table";
import { adminApi, type GenerationJob } from "@/lib/api";

export function AdminGenerationJobsPage() {
  const [filter, setFilter] = useState<{
    project_id: string;
    job_type: string;
    status: string;
  }>({ project_id: "", job_type: "", status: "" });

  const queryFilter = {
    project_id: filter.project_id || undefined,
    job_type: filter.job_type || undefined,
    status: filter.status || undefined,
  };

  const { data = [], refetch } = useQuery({
    queryKey: ["admin", "jobs", queryFilter],
    queryFn: () => adminApi.jobs(queryFilter) as Promise<GenerationJob[]>,
  });

  const cancel = async (id: string) => {
    try {
      await adminApi.cancelJob(id);
      toast.success("已取消，将写入 audit_logs");
      await refetch();
    } catch {
      toast.error("取消失败");
    }
  };

  return (
    <div className="space-y-6">
      <AdminTitle title="平台生成队列" desc="generation_jobs，支持按 project / type / status 过滤与强制取消。" />
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center gap-3">
          <CardTitle>generation_jobs</CardTitle>
          <input
            type="text"
            placeholder="project_id 过滤"
            value={filter.project_id}
            onChange={(e) => setFilter((f) => ({ ...f, project_id: e.target.value }))}
            className="h-9 w-56 rounded-lg border border-slate-200 px-3 text-sm"
          />
          <input
            type="text"
            placeholder="job_type 过滤"
            value={filter.job_type}
            onChange={(e) => setFilter((f) => ({ ...f, job_type: e.target.value }))}
            className="h-9 w-44 rounded-lg border border-slate-200 px-3 text-sm"
          />
          <select
            value={filter.status}
            onChange={(e) => setFilter((f) => ({ ...f, status: e.target.value }))}
            className="h-9 rounded-lg border border-slate-200 px-3 text-sm"
          >
            <option value="">全部状态</option>
            <option value="queued">queued</option>
            <option value="running">running</option>
            <option value="succeeded">succeeded</option>
            <option value="failed">failed</option>
            <option value="cancelled">cancelled</option>
          </select>
          <Button size="sm" variant="ghost" onClick={() => refetch()}>
            刷新
          </Button>
        </CardHeader>
        <CardContent>
          {data.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">无匹配任务。</p>
          ) : (
            <AdminJobsTable rows={data} onCancel={cancel} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
