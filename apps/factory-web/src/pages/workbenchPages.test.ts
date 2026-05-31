import { describe, expect, it } from "vitest";
import { workbenchPages } from "./workbenchPages";

describe("Goal3 内部工作台页面配置", () => {
  it("覆盖 13 个验收页面", () => {
    expect(workbenchPages.map((page) => page.acceptanceName)).toEqual([
      "Data Overview",
      "Parameter Library",
      "Claim Library",
      "Comment Topic Library",
      "User Task Library",
      "Target Group Library",
      "Battlefield Library",
      "Mapping Workbench",
      "SKU Results",
      "SKU Detail",
      "Competitor Results",
      "Calibration Report",
      "Runtime Export Preview"
    ]);
  });

  it("使用内部生产线中文页面标签", () => {
    expect(workbenchPages.every((page) => !page.label.includes("客户"))).toBe(true);
    expect(workbenchPages.map((page) => page.label)).toContain("导出预览");
  });
});
