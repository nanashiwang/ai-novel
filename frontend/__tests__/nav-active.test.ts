import { describe, expect, it } from "vitest";

import { findActiveNavHref } from "@/lib/nav-active";

const studioItems = [
  { href: "/studio" },
  { href: "/studio/projects" },
  {
    href: "/studio/projects/demo-project/write",
    activePatterns: [/^\/studio\/projects\/[^/]+\/write(?:\/.*)?$/],
  },
  {
    href: "/studio/projects/demo-project/jobs",
    activePatterns: [/^\/studio\/projects\/[^/]+\/jobs(?:\/.*)?$/],
  },
];

describe("findActiveNavHref", () => {
  it("prefers the most specific item", () => {
    expect(findActiveNavHref("/studio/projects/demo-project/write", studioItems)).toBe(
      "/studio/projects/demo-project/write",
    );
  });

  it("matches nested pages under the active item", () => {
    expect(findActiveNavHref("/studio/projects/demo-project/write/scene-1", studioItems)).toBe(
      "/studio/projects/demo-project/write",
    );
  });

  it("keeps projects active only for project list pages", () => {
    expect(findActiveNavHref("/studio/projects", studioItems)).toBe("/studio/projects");
    expect(findActiveNavHref("/studio/projects/new", studioItems)).toBe("/studio/projects");
  });

  it("matches dynamic project write and jobs pages", () => {
    expect(findActiveNavHref("/studio/projects/project_123/write", studioItems)).toBe(
      "/studio/projects/demo-project/write",
    );
    expect(findActiveNavHref("/studio/projects/project_123/jobs", studioItems)).toBe(
      "/studio/projects/demo-project/jobs",
    );
  });
});
