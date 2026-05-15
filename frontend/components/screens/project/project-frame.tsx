"use client";

import Link from "next/link";
import { MoreHorizontal, Play, ScrollText } from "lucide-react";
import { usePathname } from "next/navigation";
import { toast } from "sonner";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs } from "@/components/ui/tabs";
import { getProject } from "@/lib/mock-data";
import { projectNav } from "@/lib/routes";

export function ProjectHeader({ projectId = "demo-project" }: { projectId?: string }) {
  const pathname = usePathname();
  const project = getProject(projectId);
  const tabs = projectNav.map((item) => ({ label: item.label, href: item.href.replace("demo-project", project.id) }));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2 text-sm text-slate-500">
            <Link href="/studio">工作台</Link><span>/</span><Link href="/studio/projects">项目</Link><span>/</span><span>{project.title}</span>
          </div>
          <h1 className="text-3xl font-black text-slate-950">{project.title}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge tone="blue">组织：personal-workspace</Badge>
            <StatusBadge status={project.status} />
            <Badge tone="violet">第 {project.currentChapterIndex ?? 1} 章</Badge>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => toast.success("已创建 generation_job 并启动 Temporal Workflow（mock）")}><Play className="size-4" /> 继续生成下一章</Button>
          <Link href={`/studio/projects/${project.id}/jobs`}><Button variant="secondary"><ScrollText className="size-4" /> 查看 Workflow 日志</Button></Link>
          <Button variant="ghost" onClick={() => toast.info("管理员更多菜单：model_calls / org 用量 / 强制取消")}> <MoreHorizontal className="size-4" /> 更多</Button>
        </div>
      </div>
      <Tabs tabs={tabs} activeHref={pathname} />
    </div>
  );
}
