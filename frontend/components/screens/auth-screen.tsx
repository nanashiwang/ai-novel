"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Github, Mail, ShieldCheck, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useMockAuth } from "@/components/providers/mock-auth-provider";

export function AuthScreen({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const { setRole } = useMockAuth();
  const isLogin = mode === "login";

  const submit = () => {
    setRole("writer");
    toast.success(isLogin ? "已使用 mock 身份登录" : "已创建个人组织并绑定 Free 套餐（mock）");
    router.push("/studio");
  };

  return (
    <main className="grid min-h-screen bg-slate-950 lg:grid-cols-[1.05fr_0.95fr]">
      <section className="relative hidden overflow-hidden p-10 text-white lg:block">
        <div className="absolute inset-0 bg-gradient-to-br from-slate-950 via-[#11194a] to-indigo-950" />
        <Image src="/mock-assets/login-illustration.png" alt="小说氛围插图" fill sizes="50vw" className="object-cover opacity-35 mix-blend-screen" priority />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,rgba(139,92,246,0.45),transparent_30rem)]" />
        <div className="relative z-10 flex h-full flex-col justify-between">
          <div className="flex items-center gap-3">
            <div className="grid size-12 place-items-center rounded-full border border-violet-300/40 bg-white/10">
              <Sparkles className="size-7 text-violet-200" />
            </div>
            <div>
              <p className="text-2xl font-black">NovelFlow AI</p>
              <p className="text-sm text-indigo-100">自动小说生产平台</p>
            </div>
          </div>
          <div className="max-w-2xl">
            <p className="mb-4 inline-flex rounded-full border border-white/15 bg-white/10 px-4 py-2 text-sm text-indigo-100">SaaS 多租户 · Workflow 驱动 · 长篇记忆</p>
            <h1 className="text-5xl font-black leading-tight tracking-tight">把故事圣经、大纲、场景正文和审稿工作流放进同一个专业工作台。</h1>
            <p className="mt-5 text-lg leading-8 text-slate-200">不是聊天窗口，而是面向长期商业化运营的 AI 小说生产系统。</p>
          </div>
        </div>
      </section>
      <section className="grid place-items-center bg-slate-50 p-6">
        <div className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-7 shadow-xl shadow-slate-200/70">
          <div className="mb-6 text-center">
            <p className="text-sm font-bold text-indigo-600">{isLogin ? "欢迎回来" : "创建工作区"}</p>
            <h2 className="mt-2 text-3xl font-black text-slate-950">{isLogin ? "登录 NovelFlow" : "注册 NovelFlow"}</h2>
            <p className="mt-2 text-sm text-slate-500">第一阶段为 mock auth，不会连接真实账号系统。</p>
          </div>
          <div className="space-y-4">
            <label className="block text-sm font-semibold text-slate-700">
              邮箱
              <input className="mt-2 h-12 w-full rounded-xl border border-slate-200 px-4 outline-none focus:border-indigo-500" defaultValue={isLogin ? "writer@example.com" : "new-writer@example.com"} />
            </label>
            <label className="block text-sm font-semibold text-slate-700">
              密码
              <input type="password" className="mt-2 h-12 w-full rounded-xl border border-slate-200 px-4 outline-none focus:border-indigo-500" defaultValue="novelflow-demo" />
            </label>
            {!isLogin ? (
              <label className="block text-sm font-semibold text-slate-700">
                组织名称
                <input className="mt-2 h-12 w-full rounded-xl border border-slate-200 px-4 outline-none focus:border-indigo-500" defaultValue="personal-workspace" />
              </label>
            ) : null}
            <Button className="w-full" size="lg" onClick={submit}>{isLogin ? "登录工作台" : "注册并创建个人组织"}</Button>
            <div className="grid grid-cols-2 gap-3">
              <Button variant="secondary" onClick={() => toast.info("第三方登录为 mock action")}> <Github className="size-4" /> GitHub</Button>
              <Button variant="secondary" onClick={() => toast.info("验证码登录为 mock action")}> <Mail className="size-4" /> 验证码</Button>
            </div>
          </div>
          <div className="mt-6 flex items-center justify-between text-sm">
            <Link href={isLogin ? "/auth/register" : "/auth/login"} className="font-semibold text-indigo-600 hover:text-indigo-700">
              {isLogin ? "没有账号？注册" : "已有账号？登录"}
            </Link>
            <button
              type="button"
              className="inline-flex items-center gap-1 font-semibold text-slate-500 hover:text-slate-950"
              onClick={() => {
                setRole("admin");
                toast.success("已切换为 super_admin mock 身份");
                router.push("/admin");
              }}
            >
              <ShieldCheck className="size-4" /> Admin Console
            </button>
          </div>
          {!isLogin ? <p className="mt-5 rounded-2xl bg-indigo-50 p-4 text-xs leading-6 text-indigo-700">注册后将创建个人组织、绑定 Free 套餐，并生成默认配额；本阶段仅为前端展示。</p> : null}
        </div>
      </section>
    </main>
  );
}
