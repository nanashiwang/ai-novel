import { AppShell } from "@/components/layout/app-shell";

export default function StudioLayout({ children }: { children: React.ReactNode }) {
  return <AppShell mode="studio">{children}</AppShell>;
}
