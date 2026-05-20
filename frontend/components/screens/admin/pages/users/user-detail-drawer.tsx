"use client";

import { useQuery } from "@tanstack/react-query";

import { Badge, PlanBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { adminApi } from "@/lib/api";

export type UserDetailDrawerProps = {
  userId: string;
  onClose: () => void;
};

export function UserDetailDrawer({ userId, onClose }: UserDetailDrawerProps) {
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "user", userId],
    queryFn: () => adminApi.user(userId),
  });
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>用户详情</CardTitle>
        <Button size="sm" variant="ghost" onClick={onClose}>
          关闭
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading || !data ? (
          <p className="text-sm text-slate-500">加载中…</p>
        ) : (
          <>
            <div className="space-y-1 text-sm">
              <p className="font-bold text-slate-950">{data.display_name}</p>
              <p className="text-slate-500">{data.email}</p>
              <p className="text-xs text-slate-400">user_id: {data.id}</p>
            </div>
            <div>
              <p className="mb-2 text-sm font-bold text-slate-700">所属组织</p>
              {data.organizations.length === 0 ? (
                <p className="text-sm text-slate-500">未加入任何组织。</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {data.organizations.map((org) => (
                    <li
                      key={org.organization_id}
                      className="flex items-center justify-between rounded-lg border border-slate-200 p-3"
                    >
                      <div>
                        <p className="font-semibold text-slate-900">{org.organization_name}</p>
                        <p className="text-xs text-slate-500">{org.organization_id}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge tone="blue">{org.role}</Badge>
                        <PlanBadge plan={org.plan_code as never} />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
