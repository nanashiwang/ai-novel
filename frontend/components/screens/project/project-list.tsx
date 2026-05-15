"use client";

import Link from "next/link";
import { Filter, Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { ProgressBar } from "@/components/ui/progress";
import { StatusBadge } from "@/components/ui/badge";
import { projects } from "@/lib/mock-data";
import { formatNumber } from "@/lib/format";

export function ProjectListPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black text-slate-950">小说项目</h1>
          <p className="mt-1 text-slate-500">按项目状态、类型、章节进度和最近产出管理长篇生产。</p>
        </div>
        <Link href="/studio/projects/new"><Button><Plus className="size-4" /> 新建小说项目</Button></Link>
      </div>
      <Card>
        <CardContent className="flex flex-wrap items-center gap-3">
          <div className="flex h-11 min-w-80 items-center gap-2 rounded-xl border border-slate-200 px-3 text-slate-500">
            <Search className="size-4" /><input className="w-full outline-none" placeholder="搜索项目、标签、类型" />
          </div>
          <Button variant="secondary"><Filter className="size-4" /> 状态筛选</Button>
          <Button variant="secondary">类型筛选</Button>
        </CardContent>
      </Card>
      <DataTable
        rows={projects}
        columns={[
          { key: "project", header: "项目", render: (row) => <div><Link href={`/studio/projects/${row.id}`} className="font-bold text-slate-950 hover:text-indigo-600">{row.title}</Link><p className="text-xs text-slate-500">{row.tags.join(" / ")}</p></div> },
          { key: "genre", header: "类型", render: (row) => row.genre },
          { key: "status", header: "状态", render: (row) => <StatusBadge status={row.status} /> },
          { key: "chapters", header: "章节进度", render: (row) => <div className="min-w-40"><div className="mb-1 text-xs text-slate-500">{row.completedChapterCount} / {row.targetChapterCount}</div><ProgressBar value={(row.completedChapterCount / row.targetChapterCount) * 100} tone="green" /></div> },
          { key: "words", header: "字数", render: (row) => `${formatNumber(row.currentWordCount)} / ${formatNumber(row.targetWordCount)}` },
          { key: "updated", header: "最近更新", render: (row) => row.updatedAt.slice(0, 10) },
          { key: "actions", header: "操作", render: (row) => <div className="flex gap-2"><Link href={`/studio/projects/${row.id}/write`}><Button size="sm" variant="secondary">写作</Button></Link><Link href={`/studio/projects/${row.id}/jobs`}><Button size="sm" variant="ghost">任务</Button></Link></div> },
        ]}
      />
    </div>
  );
}
