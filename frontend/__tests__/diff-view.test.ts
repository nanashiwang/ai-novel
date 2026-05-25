import { describe, expect, it } from "vitest";

import { buildDiffRows } from "@/components/ui/diff-view";

describe("buildDiffRows", () => {
  it("marks added and removed lines with line numbers", () => {
    const rows = buildDiffRows("第一行\n删除行\n保留行", "第一行\n新增行\n保留行");

    expect(rows.map((row) => row.kind)).toEqual([
      "unchanged",
      "removed",
      "added",
      "unchanged",
    ]);
    expect(rows[1]).toMatchObject({
      kind: "removed",
      text: "删除行",
      oldLineNumber: 2,
      newLineNumber: null,
    });
    expect(rows[2]).toMatchObject({
      kind: "added",
      text: "新增行",
      oldLineNumber: null,
      newLineNumber: 2,
    });
  });

  it("preserves blank lines inside changed blocks", () => {
    const rows = buildDiffRows("A\n\nB\n", "A\n\nC\n");

    expect(rows.map((row) => row.text)).toEqual(["A", "", "B", "C"]);
    expect(rows.map((row) => row.kind)).toEqual([
      "unchanged",
      "unchanged",
      "removed",
      "added",
    ]);
  });
});
