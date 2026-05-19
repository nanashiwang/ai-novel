"use client";

import { useQuery } from "@tanstack/react-query";
import { Filter, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { ProgressBar } from "@/components/ui/progress";
import { projectsApi, type Project } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { useScopedKey } from "@/lib/use-scoped-key";

export function ProjectListPage() {
  const [keyword, setKeyword] = useState("");
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: useScopedKey("projects"),
    queryFn: () => projectsApi.list(),
  });

  const projects = (data ?? []).filter((p) =>
    keyword ? p.title.includes(keyword) || p.genre.includes(keyword) : true,
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black text-slate-950">小说项目</h1>
          <p className="mt-1 text-slate-500">按项目状态、类型管理长篇生产。</p>
        </div>
        <Link href="/studio/projects/new">
          <Button>
            <Plus className="size-4" /> 新建小说项目
          </Button>
        </Link>
      </div>
      <Card>
        <CardContent className="flex flex-wrap items-center gap-3">
          <div className="flex h-11 min-w-80 items-center gap-2 rounded-xl border border-slate-200 px-3 text-slate-500">
            <Search className="size-4" />
            <input
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              className="w-full outline-none"
              placeholder="搜索项目、类型"
            />
          </div>
          <Button variant="secondary">
            <Filter className="size-4" /> 状态筛选
          </Button>
          <Button variant="secondary" onClick={() => refetch()}>
            刷新
          </Button>
        </CardContent>
      </Card>

      {isPending ? (
        <Card>
          <CardContent className="p-12 text-center text-slate-500">加载中…</CardContent>
        </Card>
      ) : isError ? (
        <Card>
          <CardContent className="p-12 text-center text-rose-500">
            加载失败，请稍后重试
          </CardContent>
        </Card>
      ) : projects.length === 0 ? (
        <Card>
          <CardContent className="space-y-3 p-12 text-center">
            <p className="text-lg font-bold text-slate-950">暂无项目</p>
            <p className="text-slate-500">点击右上角“新建小说项目”开始你的第一部长篇。</p>
          </CardContent>
        </Card>
      ) : (
        <DataTable
          rows={projects as Project[]}
          columns={[
            {
              key: "project",
              header: "项目",
              render: (row) => (
                <div>
                  <Link
                    href={`/studio/projects/${row.id}`}
                    className="font-bold text-slate-950 hover:text-indigo-600"
                  >
                    {row.title}
                  </Link>
                  <p className="text-xs text-slate-500">{row.style}</p>
                </div>
              ),
            },
            { key: "genre", header: "类型", render: (row) => row.genre || "—" },
            {
              key: "status",
              header: "状态",
              render: (row) => <StatusBadge status={row.status as never} />,
            },
            {
              key: "chapters",
              header: "目标章节",
              render: (row) => (
                <div className="min-w-40">
                  <div className="mb-1 text-xs text-slate-500">0 / {row.target_chapter_count}</div>
                  <ProgressBar value={0} tone="green" />
                </div>
              ),
            },
            {
              key: "words",
              header: "目标字数",
              render: (row) => `${formatNumber(row.target_word_count)}`,
            },
            {
              key: "actions",
              header: "操作",
              render: (row) => (
                <div className="flex gap-2">
                  <Link href={`/studio/projects/${row.id}`}>
                    <Button size="sm">总览</Button>
                  </Link>
                  <Link href={`/studio/projects/${row.id}/write`}>
                    <Button size="sm" variant="ghost">
                      写作
                    </Button>
                  </Link>
                  <Link href={`/studio/projects/${row.id}/jobs`}>
                    <Button size="sm" variant="ghost">
                      任务
                    </Button>
                  </Link>
                </div>
              ),
            },
          ]}
        />
      )}
    </div>
  );
}
