import { AdminProtected } from "@/components/layout/admin-protected";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <AdminProtected>{children}</AdminProtected>;
}
