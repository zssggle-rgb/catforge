export const workbenchPages = [
  { key: "wb-data-overview", label: "数据概览", acceptanceName: "Data Overview", group: "source" },
  { key: "wb-parameters", label: "标准参数库", acceptanceName: "Parameter Library", group: "library" },
  { key: "wb-claims", label: "标准卖点库", acceptanceName: "Claim Library", group: "library" },
  { key: "wb-comment-topics", label: "评论主题库", acceptanceName: "Comment Topic Library", group: "library" },
  { key: "wb-tasks", label: "用户任务库", acceptanceName: "User Task Library", group: "library" },
  { key: "wb-target-groups", label: "目标人群库", acceptanceName: "Target Group Library", group: "library" },
  { key: "wb-battlefields", label: "价值战场库", acceptanceName: "Battlefield Library", group: "library" },
  { key: "wb-mappings", label: "映射规则", acceptanceName: "Mapping Workbench", group: "library" },
  { key: "wb-sku-results", label: "SKU 批量结果", acceptanceName: "SKU Results", group: "result" },
  { key: "wb-sku-detail", label: "单 SKU 质检", acceptanceName: "SKU Detail", group: "result" },
  { key: "wb-competitors", label: "竞品证据", acceptanceName: "Competitor Results", group: "result" },
  { key: "wb-calibration", label: "市场校准", acceptanceName: "Calibration Report", group: "release" },
  { key: "wb-export-preview", label: "导出预览", acceptanceName: "Runtime Export Preview", group: "release" }
] as const;

export type WorkbenchPageKey = (typeof workbenchPages)[number]["key"];

export function isWorkbenchPageKey(value: string): value is WorkbenchPageKey {
  return workbenchPages.some((page) => page.key === value);
}
