import { RequireAuth } from "@/components/auth/require-auth";
import { AppShell } from "@/components/layout/app-shell";

export default function StudioLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <AppShell mode="studio">{children}</AppShell>
    </RequireAuth>
  );
}
