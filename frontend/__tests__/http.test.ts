import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  getAccessToken,
  getOrganizationId,
  http,
  onAuthExpired,
  setAccessToken,
  setOrganizationId,
} from "@/lib/http";

describe("http token store", () => {
  beforeEach(() => {
    setAccessToken(null);
    setOrganizationId(null);
  });

  it("setAccessToken / getAccessToken roundtrip", () => {
    setAccessToken("abc");
    expect(getAccessToken()).toBe("abc");
  });

  it("setOrganizationId persists to localStorage", () => {
    setOrganizationId("org_1");
    expect(getOrganizationId()).toBe("org_1");
    expect(window.localStorage.getItem("novelflow_org_id")).toBe("org_1");
    setOrganizationId(null);
    expect(window.localStorage.getItem("novelflow_org_id")).toBeNull();
  });

  it("onAuthExpired listener fires on event", () => {
    const listener = vi.fn();
    const unsubscribe = onAuthExpired(listener);
    window.dispatchEvent(new CustomEvent("novelflow:auth_expired"));
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
    window.dispatchEvent(new CustomEvent("novelflow:auth_expired"));
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("ApiError carries status / code / message", () => {
    const err = new ApiError(403, "permission_denied", "no perm", { reason: "x" });
    expect(err.status).toBe(403);
    expect(err.code).toBe("permission_denied");
    expect(err.details).toEqual({ reason: "x" });
  });

  it("http exposes put helper", () => {
    expect(typeof http.put).toBe("function");
  });
});
