export const screenFiles = import.meta.glob<string>("./screens/*.html", {
  eager: true, query: "?raw", import: "default"
});
export function screenMarkup(id: string): string {
  const html = screenFiles["./screens/" + id + ".html"];
  if (!html) throw new Error("缺少工作台页面 " + id);
  return html;
}

// Screen IDs and business fields are independent of CSS selectors and database column names.
export const detailScreens = {
  "own-evidence": ["evidenceModal", "价格异常证据链"],
  "rival-evidence": ["rivalEvidenceModal", "竞品调价证据"],
  "rival-price-history": ["rivalPriceDetailModal", "竞品价格明细"],
  "rival-price-summary": ["rivalPriceModal", "竞品调价详情"],
  "launch-encyclopedia": ["launchEncyclopediaModal", "竞品百科"],
  "product-profile": ["competitorWikiModal", "产品档案"],
  "task": ["todoDetailModal", "待办任务详情"],
  "report": ["reportDetailModal", "报告详情"]
} as const;
export type DetailKind = keyof typeof detailScreens;
