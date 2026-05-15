import type { Metadata } from "next";
import { cookies } from "next/headers";
import { Toaster } from "sonner";
import { MockAuthProvider, type MockRole } from "@/components/providers/mock-auth-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "NovelFlow AI",
  description: "AI 小说自动生产 SaaS 平台前端 UI 壳",
};

function normalizeInitialRole(value: string | undefined): MockRole {
  return value === "admin" || value === "writer" ? value : "writer";
}

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const cookieStore = await cookies();
  const initialRole = normalizeInitialRole(cookieStore.get("novelflow_mock_role")?.value);

  return (
    <html lang="zh-CN" data-scroll-behavior="smooth">
      <body>
        <MockAuthProvider initialRole={initialRole}>
          {children}
          <Toaster richColors position="top-center" />
        </MockAuthProvider>
      </body>
    </html>
  );
}
