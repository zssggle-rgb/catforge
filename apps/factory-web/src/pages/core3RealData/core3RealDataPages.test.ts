import { describe, expect, it } from "vitest";
import { workbenchPages } from "../workbenchPages";
import { core3Pages } from "../core3/core3Pages";
import {
  core3RealDataPages,
  core3RealDataRoleOrder,
  defaultCore3RealDataPageKey,
  isCore3RealDataPageKey
} from "./core3RealDataPages";

describe("Core3 真实数据页面配置", () => {
  it("独立于旧三竞品页面和 Goal3 工作台", () => {
    const oldKeys = new Set<string>([...core3Pages.map((page) => page.key), ...workbenchPages.map((page) => page.key)]);
    expect(core3RealDataPages.every((page) => !oldKeys.has(page.key))).toBe(true);
    expect(core3RealDataPages.every((page) => page.key.startsWith("core3-real-data-"))).toBe(true);
  });

  it("默认进入核心竞品报告", () => {
    expect(defaultCore3RealDataPageKey).toBe("core3-real-data-report");
    expect(isCore3RealDataPageKey(defaultCore3RealDataPageKey)).toBe(true);
    expect(isCore3RealDataPageKey("core3-report")).toBe(false);
  });

  it("三竞品角色顺序符合业务汇报口径", () => {
    expect(core3RealDataRoleOrder).toEqual(["direct_fight", "price_volume_pressure", "benchmark_potential"]);
  });
});
