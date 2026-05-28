"use client";

/**
 * useEventSource：订阅项目维度 SSE 推送，自动重连 + 类型过滤。
 *
 * 后端在 ``GET /api/v1/projects/{id}/events`` 用 ``text/event-stream``
 * 推任务状态变化。本 hook 把 ``EventSource`` 封装成可在 React 组件里
 * 安全使用的订阅，断开时按指数退避自动重连。
 *
 * 鉴权：``EventSource`` 不能带自定义 header，access_token 通过 query
 * string ``?token=`` 传给后端；token 来自 `lib/http` 模块单例。
 *
 * 用法：
 *   useProjectEvents(projectId, {
 *     onJobUpdate: (payload) => queryClient.invalidateQueries(...),
 *   });
 *
 * 设计要点：
 * - ``enabled=false`` 时不连接（用于无 projectId / 未登录场景）。
 * - 第一个 ``event: ready`` 不分发给业务回调，仅记录订阅成功；
 *   ``event: ping`` 也只用来重置退避，不分发。
 * - 重连退避：1s → 2s → 4s → 8s → 30s 上限，避免雪崩。
 * - 组件卸载 / projectId 变化 / 重新登录后 token 变化都会重连。
 */

import { useEffect, useRef } from "react";

import { getAccessToken } from "@/lib/http";

const RECONNECT_INITIAL_MS = 1000;
const RECONNECT_MAX_MS = 30000;

export type ProjectEventType =
  | "job.queued"
  | "job.running"
  | "job.succeeded"
  | "job.failed"
  | "job.cancelled"
  | "character_revision.created"
  | "scene.updated"
  | "batch_job.started"
  | "batch_job.item_started"
  | "batch_job.item_succeeded"
  | "batch_job.item_failed"
  | "batch_job.completed"
  | "batch_job.failed"
  | "ping";

export type ProjectEvent = {
  type: ProjectEventType;
  payload: Record<string, unknown>;
  ts: string;
};

export type UseEventSourceOptions = {
  /** 关闭时不建立连接（默认 true）。 */
  enabled?: boolean;
  /** 收到 message 事件后的统一回调。 */
  onMessage?: (event: ProjectEvent) => void;
  /** 仅订阅这些 type；不传则全量。 */
  filter?: ReadonlyArray<ProjectEventType>;
  /** 连接成功时触发，可用来重置 UI 状态。 */
  onReady?: () => void;
};

/**
 * 通用版本：传入 SSE 路径（不含 ``?token=``）。
 *
 * ``path`` 形如 ``/projects/${projectId}/events``。完整 URL 由 hook
 * 内部根据 ``NEXT_PUBLIC_API_BASE`` 拼接，与 ``lib/http`` 同源。
 */
/**
 * 创建一个 EventSource 订阅连接（不依赖 React），可独立单元测试。
 *
 * - 返回 ``disconnect`` 函数，调用即关闭并停止重连。
 * - ``getToken`` 注入以便测试 / SSR；默认用 ``lib/http`` 的内存 token。
 */
export type CreateEventSourceConnectionOptions = UseEventSourceOptions & {
  /** SSE 路径，例如 ``/projects/p1/events``。 */
  path: string;
  /** 自定义 token 获取（默认 ``getAccessToken``）。 */
  getToken?: () => string | null;
  /** EventSource 构造器注入（jsdom / SSR 时可替换为 fake）。 */
  EventSourceImpl?: typeof EventSource;
  /** API base，默认读 ``NEXT_PUBLIC_API_BASE``，回落到 ``/api/v1``。 */
  apiBase?: string;
};

export function createEventSourceConnection(
  options: CreateEventSourceConnectionOptions,
): () => void {
  const {
    path,
    onMessage,
    filter,
    onReady,
    getToken = getAccessToken,
    EventSourceImpl = typeof EventSource !== "undefined" ? EventSource : undefined,
    apiBase = (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE) || "/api/v1",
  } = options;

  if (!path || !EventSourceImpl) {
    return () => undefined;
  }

  let cancelled = false;
  let es: EventSource | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let backoff = RECONNECT_INITIAL_MS;

  const cleanup = () => {
    if (es) {
      es.close();
      es = null;
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  const scheduleReconnect = () => {
    cleanup();
    if (cancelled) return;
    reconnectTimer = setTimeout(connect, backoff);
    backoff = Math.min(backoff * 2, RECONNECT_MAX_MS);
  };

  function connect() {
    if (cancelled) return;
    const token = getToken();
    if (!token) {
      reconnectTimer = setTimeout(connect, backoff);
      return;
    }
    const base = apiBase.replace(/\/$/, "");
    const url = `${base}${path.startsWith("/") ? path : `/${path}`}?token=${encodeURIComponent(
      token,
    )}`;

    try {
      es = new EventSourceImpl!(url);
    } catch {
      scheduleReconnect();
      return;
    }

    es.addEventListener("ready", () => {
      backoff = RECONNECT_INITIAL_MS;
      onReady?.();
    });

    es.addEventListener("ping", () => {
      backoff = RECONNECT_INITIAL_MS;
    });

    es.addEventListener("message", (raw) => {
      backoff = RECONNECT_INITIAL_MS;
      let parsed: ProjectEvent | null = null;
      try {
        parsed = JSON.parse((raw as MessageEvent<string>).data) as ProjectEvent;
      } catch {
        return;
      }
      if (!parsed || !parsed.type) return;
      if (filter && !filter.includes(parsed.type)) return;
      onMessage?.(parsed);
    });

    es.onerror = () => {
      scheduleReconnect();
    };
  }

  connect();

  return () => {
    cancelled = true;
    cleanup();
  };
}

export function useEventSource(path: string, options: UseEventSourceOptions = {}) {
  const { enabled = true, onMessage, filter, onReady } = options;
  const onMessageRef = useRef(onMessage);
  const onReadyRef = useRef(onReady);
  const filterRef = useRef(filter);

  // 在 effect 中同步最新回调，避免每次 render 重连
  useEffect(() => {
    onMessageRef.current = onMessage;
    onReadyRef.current = onReady;
    filterRef.current = filter;
  });

  useEffect(() => {
    if (!enabled || !path) return;
    if (typeof window === "undefined") return;
    if (typeof EventSource === "undefined") return;

    const disconnect = createEventSourceConnection({
      path,
      onMessage: (ev) => onMessageRef.current?.(ev),
      onReady: () => onReadyRef.current?.(),
      filter: filterRef.current,
    });
    return disconnect;
  }, [enabled, path]);
}

/**
 * 项目维度封装：用项目 ID 自动拼路径。
 *
 * 推荐绝大多数页面用这个版本，而不是 useEventSource 通用形式。
 */
export function useProjectEvents(
  projectId: string | null | undefined,
  options: UseEventSourceOptions = {},
) {
  const enabled = options.enabled ?? Boolean(projectId);
  const path = projectId ? `/projects/${projectId}/events` : "";
  useEventSource(path, { ...options, enabled });
}
