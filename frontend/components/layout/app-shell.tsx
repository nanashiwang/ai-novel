"use client";

import { AdminSidebar } from "./admin-sidebar";
import { StudioSidebar } from "./studio-sidebar";
import { Topbar } from "./topbar";

export function AppShell({ children, mode = "studio" }: { children: React.ReactNode; mode?: "studio" | "admin" }) {
  return (
    <div className="min-h-screen">
      {mode === "admin" ? <AdminSidebar /> : <StudioSidebar />}
      <div className="lg:pl-[278px]">
        {mode === "admin" ? <div className="lg:pl-[6px]"><Topbar mode="admin" /></div> : <Topbar mode="studio" />}
        <main className="px-4 py-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
