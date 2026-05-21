/**
 * createEventSourceConnection 单元测试。
 *
 * hook 内部用 useEffect 包装这个底层函数；将逻辑抽出后可以在
 * 不引入 @testing-library/react 的情况下覆盖核心路径。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createEventSourceConnection } from "@/lib/hooks/use-event-source";

type Listener = (ev: unknown) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  url: string;
  onerror: Listener | null = null;
  closed = false;
  listeners: Record<string, Listener[]> = {};

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, fn: Listener) {
    (this.listeners[type] ||= []).push(fn);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, payload: { data?: string } = {}) {
    (this.listeners[type] || []).forEach((fn) => fn({ ...payload, type } as MessageEvent));
  }

  triggerError() {
    this.onerror?.({ type: "error" });
  }
}

describe("createEventSourceConnection", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeEventSource.instances.length = 0;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("path 为空时返回 noop disconnect", () => {
    const disconnect = createEventSourceConnection({
      path: "",
      getToken: () => "t",
      EventSourceImpl: FakeEventSource as unknown as typeof EventSource,
    });
    expect(FakeEventSource.instances).toHaveLength(0);
    disconnect();
  });

  it("自动拼 URL 并带上 token", () => {
    const disconnect = createEventSourceConnection({
      path: "/projects/p1/events",
      getToken: () => "test-jwt",
      EventSourceImpl: FakeEventSource as unknown as typeof EventSource,
    });
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.instances[0].url).toContain(
      "/projects/p1/events?token=test-jwt",
    );
    disconnect();
    expect(FakeEventSource.instances[0].closed).toBe(true);
  });

  it("派发 message 回调", () => {
    const onMessage = vi.fn();
    createEventSourceConnection({
      path: "/projects/p1/events",
      getToken: () => "t",
      EventSourceImpl: FakeEventSource as unknown as typeof EventSource,
      onMessage,
    });
    FakeEventSource.instances[0].emit("message", {
      data: JSON.stringify({ type: "job.succeeded", payload: { job_id: "j1" }, ts: "" }),
    });
    expect(onMessage).toHaveBeenCalledTimes(1);
    expect(onMessage.mock.calls[0][0].type).toBe("job.succeeded");
  });

  it("filter 排除不在白名单的事件", () => {
    const onMessage = vi.fn();
    createEventSourceConnection({
      path: "/projects/p1/events",
      getToken: () => "t",
      EventSourceImpl: FakeEventSource as unknown as typeof EventSource,
      filter: ["job.succeeded"],
      onMessage,
    });
    const inst = FakeEventSource.instances[0];
    inst.emit("message", { data: JSON.stringify({ type: "job.queued", payload: {}, ts: "" }) });
    expect(onMessage).not.toHaveBeenCalled();
    inst.emit("message", {
      data: JSON.stringify({ type: "job.succeeded", payload: {}, ts: "" }),
    });
    expect(onMessage).toHaveBeenCalledTimes(1);
  });

  it("error 后按退避重连", () => {
    createEventSourceConnection({
      path: "/projects/p1/events",
      getToken: () => "t",
      EventSourceImpl: FakeEventSource as unknown as typeof EventSource,
    });
    const first = FakeEventSource.instances[0];
    first.triggerError();
    expect(first.closed).toBe(true);
    vi.advanceTimersByTime(1100);
    expect(FakeEventSource.instances).toHaveLength(2);
  });

  it("ready 事件回调", () => {
    const onMessage = vi.fn();
    const onReady = vi.fn();
    createEventSourceConnection({
      path: "/projects/p1/events",
      getToken: () => "t",
      EventSourceImpl: FakeEventSource as unknown as typeof EventSource,
      onMessage,
      onReady,
    });
    FakeEventSource.instances[0].emit("ready", { data: JSON.stringify({ channel: "x" }) });
    expect(onReady).toHaveBeenCalledTimes(1);
    expect(onMessage).not.toHaveBeenCalled();
  });

  it("没 token 时不连接但定时重试", () => {
    let token: string | null = null;
    createEventSourceConnection({
      path: "/projects/p1/events",
      getToken: () => token,
      EventSourceImpl: FakeEventSource as unknown as typeof EventSource,
    });
    expect(FakeEventSource.instances).toHaveLength(0);
    token = "t";
    vi.advanceTimersByTime(1100);
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it("disconnect 后不再重连", () => {
    const disconnect = createEventSourceConnection({
      path: "/projects/p1/events",
      getToken: () => "t",
      EventSourceImpl: FakeEventSource as unknown as typeof EventSource,
    });
    expect(FakeEventSource.instances).toHaveLength(1);
    disconnect();
    FakeEventSource.instances[0].triggerError();
    vi.advanceTimersByTime(5000);
    // 没新实例
    expect(FakeEventSource.instances).toHaveLength(1);
  });
});
