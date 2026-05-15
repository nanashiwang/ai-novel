"use client";

import { useMockAuth } from "@/components/providers/mock-auth-provider";
import { PermissionNotice } from "@/components/ui/permission-notice";
import { isPlatformAdmin } from "@/lib/permissions";
import { AppShell } from "./app-shell";

export function AdminProtected({ children }: { children: React.ReactNode }) {
  const { user } = useMockAuth();
  if (!isPlatformAdmin(user)) return <PermissionNotice />;
  return <AppShell mode="admin">{children}</AppShell>;
}
