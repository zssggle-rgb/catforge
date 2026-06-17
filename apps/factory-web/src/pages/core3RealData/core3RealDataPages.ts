export const core3RealDataPages = [
  { key: "core3-real-data-initialization", label: "初始化运行", acceptanceName: "真实数据初始化运行" },
  { key: "core3-real-data-overview", label: "真实数据总览", acceptanceName: "真实数据三竞品总览" },
  { key: "core3-real-data-report", label: "核心竞品报告", acceptanceName: "真实数据核心竞品报告" },
  { key: "core3-real-data-evidence", label: "证据追溯", acceptanceName: "真实数据证据追溯" },
  { key: "core3-real-data-pipeline", label: "生产线状态", acceptanceName: "真实数据生产线状态" }
] as const;

export type Core3RealDataPageKey = (typeof core3RealDataPages)[number]["key"];

export const defaultCore3RealDataPageKey: Core3RealDataPageKey = "core3-real-data-report";

export const core3RealDataRoleOrder = [
  "direct_fight",
  "price_volume_pressure",
  "benchmark_potential"
] as const;

export type Core3RealDataRoleCode = (typeof core3RealDataRoleOrder)[number];

export function isCore3RealDataPageKey(value: string): value is Core3RealDataPageKey {
  return core3RealDataPages.some((page) => page.key === value);
}
