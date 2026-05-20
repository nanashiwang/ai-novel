"use client";

import { Github, Mail, ShieldCheck, Sparkles } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/http";

export function AuthScreen({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const { login, register } = useAuth();
  const isLogin = mode === "login";

  // 仅在开发模式下预填 admin 凭据，便于本地演示；生产构建留空
  const devDefaults = process.env.NODE_ENV !== "production";
  const [email, setEmail] = useState(isLogin && devDefaults ? "admin@novelflow.ai" : "");
  const [password, setPassword] = useState(isLogin && devDefaults ? "admin123456" : "");
  const [displayName, setDisplayName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    try {
      const user = isLogin
        ? await login(email, password)
        : await register(email, password, displayName);
      toast.success(isLogin ? "登录成功" : "注册成功，已创建个人组织");
      router.push(user.platform_role === "user" ? "/studio" : "/studio");
    } catch (error) {
      const message =
        error instanceof ApiError
          ? localizeError(error.code, error.message)
          : "网络异常，请稍后重试";
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="grid min-h-screen bg-slate-950 lg:grid-cols-[1.05fr_0.95fr]">
      <section className="relative hidden overflow-hidden p-10 text-white lg:block">
        <div className="absolute inset-0 bg-gradient-to-br from-slate-950 via-[#11194a] to-indigo-950" />
        <Image
          src="/brand-assets/login-illustration.png"
          alt="小说氛围插图"
          fill
          sizes="50vw"
          className="object-cover opacity-35 mix-blend-screen"
          priority
        />
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
            <p className="mb-4 inline-flex rounded-full border border-white/15 bg-white/10 px-4 py-2 text-sm text-indigo-100">
              SaaS 多租户 · Workflow 驱动 · 长篇记忆
            </p>
            <h1 className="text-5xl font-black leading-tight tracking-tight">
              把故事圣经、大纲、场景正文和审稿工作流放进同一个专业工作台。
            </h1>
            <p className="mt-5 text-lg leading-8 text-slate-200">
              不是聊天窗口，而是面向长期商业化运营的 AI 小说生产系统。
            </p>
          </div>
        </div>
      </section>
      <section className="grid place-items-center bg-slate-50 p-6">
        <form
          onSubmit={handleSubmit}
          className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-7 shadow-xl shadow-slate-200/70"
        >
          <div className="mb-6 text-center">
            <p className="text-sm font-bold text-indigo-600">
              {isLogin ? "欢迎回来" : "创建工作区"}
            </p>
            <h2 className="mt-2 text-3xl font-black text-slate-950">
              {isLogin ? "登录 NovelFlow" : "注册 NovelFlow"}
            </h2>
            <p className="mt-2 text-sm text-slate-500">
              {isLogin
                ? "默认 admin 账号：admin@novelflow.ai / admin123456"
                : "注册成功后自动创建个人组织，并绑定 Free 套餐。"}
            </p>
          </div>
          <div className="space-y-4">
            <label className="block text-sm font-semibold text-slate-700">
              邮箱
              <input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-2 h-12 w-full rounded-xl border border-slate-200 px-4 outline-none focus:border-indigo-500"
              />
            </label>
            <label className="block text-sm font-semibold text-slate-700">
              密码
              <input
                type="password"
                required
                minLength={6}
                autoComplete={isLogin ? "current-password" : "new-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-2 h-12 w-full rounded-xl border border-slate-200 px-4 outline-none focus:border-indigo-500"
              />
            </label>
            {!isLogin ? (
              <label className="block text-sm font-semibold text-slate-700">
                昵称
                <input
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="可留空，默认使用邮箱前缀"
                  className="mt-2 h-12 w-full rounded-xl border border-slate-200 px-4 outline-none focus:border-indigo-500"
                />
              </label>
            ) : null}
            <Button type="submit" className="w-full" size="lg" disabled={submitting}>
              {submitting ? "提交中…" : isLogin ? "登录工作台" : "注册并创建个人组织"}
            </Button>
            <div className="grid grid-cols-2 gap-3">
              <Button
                type="button"
                variant="secondary"
                onClick={() => toast.info("第三方登录待对接")}
              >
                <Github className="size-4" /> GitHub
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => toast.info("验证码登录待对接")}
              >
                <Mail className="size-4" /> 验证码
              </Button>
            </div>
          </div>
          <div className="mt-6 flex items-center justify-between text-sm">
            <Link
              href={isLogin ? "/auth/register" : "/auth/login"}
              className="font-semibold text-indigo-600 hover:text-indigo-700"
            >
              {isLogin ? "没有账号？注册" : "已有账号？登录"}
            </Link>
            <Link
              href="/admin"
              className="inline-flex items-center gap-1 font-semibold text-slate-500 hover:text-slate-950"
            >
              <ShieldCheck className="size-4" /> Admin Console
            </Link>
          </div>
        </form>
      </section>
    </main>
  );
}

function localizeError(code: string, fallback: string): string {
  switch (code) {
    case "invalid_credentials":
      return "邮箱或密码错误";
    case "email_already_registered":
      return "该邮箱已注册";
    case "user_inactive":
      return "账号已被停用";
    case "validation_error":
      return "请检查输入格式";
    case "no_organization":
      return "账号未绑定组织，请联系管理员";
    default:
      return fallback || "登录失败";
  }
}
