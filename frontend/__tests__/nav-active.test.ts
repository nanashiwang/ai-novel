import { describe, expect, it } from "vitest";

import { findActiveNavHref } from "@/lib/nav-active";

// 反映新的 studioNav 结构：删除"写作 / 任务"穿透项，
// 用 activePatterns 让"项目"项在整个 /studio/projects/... 子树上保持高亮。
const studioItems = [
  { href: "/studio" },
  {
    href: "/studio/projects",
    activePatterns: [/^\/studio\/projects(?:\/.*)?$/],
  },
  { href: "/studio/usage" },
  { href: "/studio/account" },
];

describe("findActiveNavHref", () => {
  it("matches workbench root", () => {
    expect(findActiveNavHref("/studio", studioItems)).toBe("/studio");
  });

  it("highlights '项目' for the list page", () => {
    expect(findActiveNavHref("/studio/projects", studioItems)).toBe("/studio/projects");
  });

  it("keeps '项目' active when on /new", () => {
    expect(findActiveNavHref("/studio/projects/new", studioItems)).toBe("/studio/projects");
  });

  it("keeps '项目' active when inside a specific project", () => {
    expect(findActiveNavHref("/studio/projects/project_123", studioItems)).toBe(
      "/studio/projects",
    );
    expect(findActiveNavHref("/studio/projects/project_123/write", studioItems)).toBe(
      "/studio/projects",
    );
    expect(findActiveNavHref("/studio/projects/project_123/bible/edit", studioItems)).toBe(
      "/studio/projects",
    );
  });

  it("matches sibling top-level items", () => {
    expect(findActiveNavHref("/studio/usage", studioItems)).toBe("/studio/usage");
    expect(findActiveNavHref("/studio/account", studioItems)).toBe("/studio/account");
  });
});
