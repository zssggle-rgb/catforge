export const core3Pages = [
  { key: "core3-overview", label: "批量总览", acceptanceName: "三竞品批量总览" },
  { key: "core3-report", label: "单品报告", acceptanceName: "三竞品单品报告" },
  { key: "core3-evidence", label: "证据卡片", acceptanceName: "三竞品证据卡片" }
] as const;

export type Core3PageKey = (typeof core3Pages)[number]["key"];

export const core3RoleOrder = ["direct", "pressure", "benchmark_potential"] as const;

export function isCore3PageKey(value: string): value is Core3PageKey {
  return core3Pages.some((page) => page.key === value);
}
