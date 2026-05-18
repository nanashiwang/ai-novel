"use client";

import { RequirePlatformAdmin } from "@/components/auth/require-platform-admin";
import { AppShell } from "./app-shell";

export function AdminProtected({ children }: { children: React.ReactNode }) {
  return (
    <RequirePlatformAdmin>
      <AppShell mode="admin">{children}</AppShell>
    </RequirePlatformAdmin>
  );
}
