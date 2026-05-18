/**
 * 通用 HTTP 客户端。
 *
 * 功能：
 * - 自动注入 Authorization: Bearer <access_token>
 * - 自动注入 X-Organization-Id
 * - 401 自动调 /auth/refresh 重放一次（互斥锁防雪崩）
 * - refresh 也 401 时清空 token 并广播事件 → AuthProvider 监听后跳登录页
 * - 统一抛 ApiError
 */

const API_BASE =
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE) ||
  "http://localhost:8000/api/v1";

const AUTH_EXPIRED_EVENT = "novelflow:auth_expired";

let accessToken: string | null = null;
let currentOrganizationId: string | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

export function setOrganizationId(id: string | null) {
  currentOrganizationId = id;
  if (typeof window !== "undefined") {
    if (id) {
      window.localStorage.setItem("novelflow_org_id", id);
    } else {
      window.localStorage.removeItem("novelflow_org_id");
    }
  }
}

export function getOrganizationId() {
  if (currentOrganizationId) return currentOrganizationId;
  if (typeof window !== "undefined") {
    return window.localStorage.getItem("novelflow_org_id");
  }
  return null;
}

/** 订阅鉴权失效事件，AuthProvider 监听后跳登录页。 */
export function onAuthExpired(listener: () => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  const handler = () => listener();
  window.addEventListener(AUTH_EXPIRED_EVENT, handler);
  return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handler);
}

function emitAuthExpired() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
}

export class ApiError extends Error {
  status: number;
  code: string;
  details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
  _retried?: boolean;
};

let refreshPromise: Promise<boolean> | null = null;

async function attemptRefresh(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    })
      .then(async (res) => {
        if (!res.ok) return false;
        const data = await res.json();
        setAccessToken(data.access_token);
        if (data.user?.organization_id) {
          setOrganizationId(data.user.organization_id);
        }
        return true;
      })
      .catch(() => false)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

export async function request<T = unknown>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const url = new URL(`${API_BASE}${path}`);
  if (options.query) {
    for (const [key, value] of Object.entries(options.query)) {
      if (value === undefined || value === null) continue;
      url.searchParams.set(key, String(value));
    }
  }

  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }
  const orgId = getOrganizationId();
  if (orgId) {
    headers["X-Organization-Id"] = orgId;
  }

  const response = await fetch(url.toString(), {
    method: options.method ?? "GET",
    headers,
    credentials: "include",
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  });

  if (response.status === 204) {
    return undefined as T;
  }

  if (response.status === 401 && !options._retried && !path.startsWith("/auth/")) {
    const ok = await attemptRefresh();
    if (ok) {
      return request<T>(path, { ...options, _retried: true });
    }
    setAccessToken(null);
    setOrganizationId(null);
    emitAuthExpired();
  }

  const text = await response.text();
  const parsed = text ? safeJson(text) : undefined;

  if (!response.ok) {
    const error = (parsed as { error?: { code?: string; message?: string; details?: unknown } })
      ?.error;
    throw new ApiError(
      response.status,
      error?.code ?? "http_error",
      error?.message ?? response.statusText,
      error?.details,
    );
  }

  return parsed as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const http = {
  get: <T = unknown>(path: string, query?: RequestOptions["query"]) =>
    request<T>(path, { query }),
  post: <T = unknown>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body }),
  patch: <T = unknown>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body }),
  delete: <T = unknown>(path: string) => request<T>(path, { method: "DELETE" }),
};
