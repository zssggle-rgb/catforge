import { describe, expect, it } from "vitest";
import { workbenchPages } from "../workbenchPages";
import { csvHeader, orderCore3Roles, parseJsonl } from "./core3Format";
import { core3Pages, core3RoleOrder } from "./core3Pages";

describe("Core3 MVP 页面配置", () => {
  it("页面 key 不与 Goal3 工作台重复", () => {
    const workbenchKeys = new Set<string>(workbenchPages.map((page) => page.key));
    expect(core3Pages.every((page) => !workbenchKeys.has(page.key))).toBe(true);
  });

  it("三角色展示顺序固定", () => {
    expect(core3RoleOrder).toEqual(["direct", "pressure", "benchmark_potential"]);
    expect(
      orderCore3Roles([
        { role: "benchmark_potential", sku: "B" },
        { role: "direct", sku: "D" },
        { role: "pressure", sku: "P" }
      ]).map((item) => item.role)
    ).toEqual(["direct", "pressure", "benchmark_potential"]);
  });

  it("CSV 字段完整", () => {
    expect(
      csvHeader(
        "target_sku_code,role,competitor_sku_code,score,reason,confidence,confidence_level,review_flag,insufficient_reasons\n"
      )
    ).toEqual([
      "target_sku_code",
      "role",
      "competitor_sku_code",
      "score",
      "reason",
      "confidence",
      "confidence_level",
      "review_flag",
      "insufficient_reasons"
    ]);
  });

  it("JSONL 每行合法 JSON", () => {
    const rows = parseJsonl(
      '{"target_sku_code":"TV00029115","role":"direct","competitor_sku_code":"TV00010001","evidence_card":{}}\n' +
        '{"target_sku_code":"TV00029115","role":"pressure","competitor_sku_code":"TV00010002","evidence_card":{}}\n'
    );
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ target_sku_code: "TV00029115", role: "direct" });
  });
});
