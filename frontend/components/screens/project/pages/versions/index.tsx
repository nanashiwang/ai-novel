"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProjectHeader } from "@/components/screens/project/project-frame";

export function VersionsPage({ projectId }: { projectId: string }) {
  return (
    <div className="space-y-6">
      <ProjectHeader projectId={projectId} />
      <Card>
        <CardHeader>
          <CardTitle>版本历史</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-500">
            版本接口 GET /projects/:id/versions 已就绪，UI 展示组件待落地。
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
