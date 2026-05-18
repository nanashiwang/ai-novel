"use client";

/**
 * 真实认证 Provider。
 *
 * - access_token 仅放内存；refresh 由后端 httpOnly cookie 维护
 * - 启动时调用 /auth/refresh 自动续期；失败则视为未登录
 * - 监听 auth_expired 事件 → 跳登录页 & 清缓存
 */
import { useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import {
  authApi,
  type CurrentUser,
  type TokenResponse,
} from "@/lib/api";
import { ApiError, onAuthExpired, setAccessToken, setOrganizationId } from "@/lib/http";

type AuthContextValue = {
  user: CurrentUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<CurrentUser>;
  register: (email: string, password: string, display_name: string) => Promise<CurrentUser>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function applyTokenResponse(token: TokenResponse) {
  setAccessToken(token.access_token);
  setOrganizationId(token.user.organization_id);
  return token.user;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();

  // 启动时尝试 refresh，恢复登录状态
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const token = await authApi.refresh();
        if (!mounted) return;
        setUser(applyTokenResponse(token));
      } catch (error) {
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
          // 未登录或 refresh 失效
        }
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  // 监听 auth_expired：清缓存 + 跳登录
  useEffect(() => {
    return onAuthExpired(() => {
      setUser(null);
      queryClient.clear();
      if (pathname && !pathname.startsWith("/auth/")) {
        router.replace(`/auth/login?next=${encodeURIComponent(pathname)}`);
      }
    });
  }, [pathname, queryClient, router]);

  const login = useCallback(async (email: string, password: string) => {
    const token = await authApi.login(email, password);
    const next = applyTokenResponse(token);
    setUser(next);
    queryClient.clear();
    return next;
  }, [queryClient]);

  const register = useCallback(
    async (email: string, password: string, display_name: string) => {
      const token = await authApi.register(email, password, display_name);
      const next = applyTokenResponse(token);
      setUser(next);
      queryClient.clear();
      return next;
    },
    [queryClient],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setAccessToken(null);
      setOrganizationId(null);
      setUser(null);
      queryClient.clear();
    }
  }, [queryClient]);

  const refresh = useCallback(async () => {
    try {
      const me = await authApi.me();
      setUser(me);
    } catch {
      try {
        const token = await authApi.refresh();
        setUser(applyTokenResponse(token));
      } catch {
        setUser(null);
      }
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, login, register, logout, refresh }),
    [user, loading, login, register, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
