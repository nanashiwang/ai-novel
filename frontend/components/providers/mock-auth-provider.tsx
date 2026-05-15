"use client";

import { createContext, useContext, useMemo, useState } from "react";
import { mockAdminUser, mockNormalUser } from "@/lib/mock-data";
import type { MockUser } from "@/types";

export type MockRole = "writer" | "admin";

type MockAuthContextValue = {
  user: MockUser;
  role: MockRole;
  setRole: (role: MockRole) => void;
  toggleRole: () => void;
};

const MockAuthContext = createContext<MockAuthContextValue | null>(null);
const storageKey = "novelflow_mock_role";

export function normalizeMockRole(value: string | null | undefined): MockRole | null {
  return value === "admin" || value === "writer" ? value : null;
}

function persistRole(role: MockRole) {
  try {
    window.localStorage?.setItem(storageKey, role);
  } catch {
    // Cookie persistence is enough when localStorage is unavailable.
  }
  document.cookie = `novelflow_mock_role=${role}; path=/; max-age=2592000; SameSite=Lax`;
}

export function MockAuthProvider({ children, initialRole = "writer" }: { children: React.ReactNode; initialRole?: MockRole }) {
  const [role, setRoleState] = useState<MockRole>(initialRole);

  const setRole = (nextRole: MockRole) => {
    setRoleState(nextRole);
    persistRole(nextRole);
  };

  const value = useMemo<MockAuthContextValue>(() => {
    const user = role === "admin" ? mockAdminUser : mockNormalUser;
    return {
      user,
      role,
      setRole,
      toggleRole: () => setRole(role === "admin" ? "writer" : "admin"),
    };
  }, [role]);

  return <MockAuthContext.Provider value={value}>{children}</MockAuthContext.Provider>;
}

export function useMockAuth() {
  const context = useContext(MockAuthContext);
  if (!context) throw new Error("useMockAuth must be used within MockAuthProvider");
  return context;
}
