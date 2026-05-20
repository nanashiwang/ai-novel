"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileArchive } from "lucide-react";
import { toast } from "sonner";

import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { ProjectHeader } from "@/components/screens/project/project-frame";
import { exportsApi } from "@/lib/api";
import { formatBytes, formatDateTime } from "@/lib/format";
import { ApiError } from "@/lib/http";
import { useScopedKey } from "@/lib/use-scoped-key";

export function ExportPage({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const exportsKey = useScopedKey("project", projectId, "exports");
  const { data: files = [] } = useQuery({
    queryKey: exportsKey,
    queryFn: () => exportsApi.list(projectId),
  });
  const create = useMutation({
    mutationFn: (export_type: string) => exportsApi.create(projectId, export_type),
    onSuccess: (created) => {
      toast.success(
        `已生成 ${created.export_type.toUpperCase()}（${formatBytes(created.file_size)}）`,
      );
      queryClient.invalidateQueries({ queryKey: exportsKey });
    },
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "创建失败"),
  });
  const download = useMutation({
    mutationFn: (exportId: string) => exportsApi.download(projectId, exportId),
    onError: (e: unknown) => toast.error(e instanceof ApiError ? e.message : "下载失败"),
  });

  // Sprint 5-B 仅支持 markdown / txt；docx/epub/pdf 由 Sprint 6 接入 MinIO + 真实渲染时启用
  const formats: { value: string; label: string; supported: boolean }[] = [
    { value: "markdown", label: "Markdown", supported: true },
    { value: "txt", label: "TXT", supported: true },
    { value: "docx", label: "DOCX", supported: false },
    { value: "epub", label: "EPUB", supported: false },
    { value: "pdf", label: "PDF", supported: false },
  ];

  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <div className="grid gap-4 md:grid-cols-5">
        {formats.map((format) => (
          <Card key={format.value}>
            <CardContent className="text-center">
              <FileArchive
                className={`mx-auto size-9 ${
                  format.supported ? "text-indigo-600" : "text-slate-300"
                }`}
              />
              <h3 className="mt-3 font-black uppercase text-slate-950">
                {format.label}
              </h3>
              {!format.supported ? (
                <p className="mt-1 text-xs text-slate-400">Sprint 6 接入</p>
              ) : null}
              <Button
                className="mt-4 w-full"
                size="sm"
                onClick={() => create.mutate(format.value)}
                disabled={create.isPending || !format.supported}
              >
                {create.isPending ? "生成中..." : "开始导出"}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>最近导出文件</CardTitle>
        </CardHeader>
        <CardContent>
          {files.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">暂无导出记录。</p>
          ) : (
            <DataTable
              rows={files}
              columns={[
                {
                  key: "format",
                  header: "格式",
                  render: (row) => row.export_type.toUpperCase(),
                },
                {
                  key: "status",
                  header: "状态",
                  render: (row) => (
                    <StatusBadge
                      status={row.status === "ready" ? "succeeded" : (row.status as never)}
                    />
                  ),
                },
                {
                  key: "size",
                  header: "大小",
                  render: (row) => formatBytes(row.file_size),
                },
                {
                  key: "time",
                  header: "时间",
                  render: (row) => (row.created_at ? formatDateTime(row.created_at) : "—"),
                },
                {
                  key: "download",
                  header: "操作",
                  render: (row) =>
                    row.status === "ready" ? (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => download.mutate(row.id)}
                        disabled={download.isPending}
                      >
                        <Download className="size-4" /> 下载
                      </Button>
                    ) : null,
                },
              ]}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
