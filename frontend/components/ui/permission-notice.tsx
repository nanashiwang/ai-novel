import Link from "next/link";
import { LockKeyhole } from "lucide-react";
import { Button } from "./button";

export function PermissionNotice({ title = "无权限访问", description = "当前 mock 用户不是平台管理员，Admin Console 已隐藏。" }: { title?: string; description?: string }) {
  return (
    <div className="grid min-h-screen place-items-center bg-slate-50 p-6">
      <div className="max-w-lg rounded-3xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-rose-50 text-rose-600">
          <LockKeyhole className="size-7" />
        </div>
        <h1 className="mt-5 text-2xl font-black text-slate-950">{title}</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">{description}</p>
        <Link href="/studio" className="mt-6 inline-flex">
          <Button>返回工作台</Button>
        </Link>
      </div>
    </div>
  );
}
