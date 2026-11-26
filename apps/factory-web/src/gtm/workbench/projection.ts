// The BFF supplies business values for named slots. Markup, theme, event
// handlers, and the list of supported layouts belong to the frontend.
import { displayValue, type Cell, type Evidence } from "../contract";
import { detailScreens, screenMarkup, type DetailKind } from "./screens";

export interface DetailRef { kind: DetailKind; record_id: string; label: string }
export interface DetailProjection {
  version: "0916"; project_id: string; category_code: string; snapshot_id: string;
  kind: DetailKind; record_id: string; title: string;
  values: Record<string, Cell>; lists: Record<string,string[]>;
  tables: Record<string, {columns: string[]; rows: Cell[][]}>;
  evidence: Evidence[]; links: DetailRef[];
}

// Each entry names a field in the business contract and its destination in
// the approved template. A missing value renders as unknown.
const fields: Partial<Record<DetailKind,Record<string,string>>> = {
  "own-evidence": {level:"evidenceLevel",model:"evidenceProduct",channel:"evidenceChannel",paid_price:"evidenceCurrent",
    floor_price:"evidenceBaseline",gap:"evidenceGap",source:"evidenceMeta",snapshot_note:"evidenceSnapshot"},
  "rival-evidence": {level:"rivalEvidenceLevel",model:"rivalEvidenceProduct",channel:"rivalEvidenceChannel",
    paid_price:"rivalEvidencePrice",prior_price:"rivalEvidenceSecondValue",gap:"rivalEvidenceGap",
    source:"rivalEvidenceMeta",snapshot_note:"rivalEvidenceShot"},
  "rival-price-summary": {model:"rivalPriceProduct",channel:"rivalPriceChannel",paid_price:"rivalPriceCurrent",
    prior_price:"rivalPriceBase",gap:"rivalPriceChange",source:"rivalPriceMeta",snapshot_note:"rivalPriceShot"},
  "rival-price-history": {history:"rivalPriceDetailTableWrap"},
  "launch-encyclopedia": {brand:"launchModalBrand",brand_initial:"launchModalLogo",model:"launchModalModel",
    name:"launchModalName",subtitle:"launchModalSub",category:"launchModalCategory",position:"launchModalPosition",
    units:"launchModalSales",revenue:"launchModalRevenue",price:"launchModalPrice",launch_date:"launchModalDate",
    channel:"launchModalChannel",claims:"launchModalPoints",impact:"launchModalImpact"},
  "product-profile": {brand:"wikiBrand",model:"wikiModel",position:"wikiPosition",status:"wikiStatus",units:"wikiUnits",
    revenue:"wikiRevenue",price:"wikiPrice",launch_date:"wikiLaunchDate",channel:"wikiChannel",claims:"wikiSellingPoints",
    specs:"wikiProductInfo",impact:"wikiImpact"},
  task: {title:"todoDetailTitle",description:"todoDetailDesc",type:"todoDetailType",priority:"todoDetailPriority",
    status:"todoDetailStatus",deadline:"todoDetailDeadline",owner:"todoDetailOwner"},
  report: {title:"detailReportTitle",metadata:"detailReportMeta",monitored_skus:"detailKpiSku",price_changes:"detailKpiChange",
    tasks:"detailKpiAction",summary:"detailReportSummary",versions:"detailVersionTimeline"}
};
const fixed = new Set(("当前到手价 月度底价 价格偏差 价格变动 价格记录 上次到手价 价格明细 历史价格对比 产品信息 核心卖点 对我品的影响判断 品牌 产品型号 品类 市场定位 近30天销量 近30天销额 当前均价 上市日期 首发渠道 任务类型 优先级 状态 截止时间 负责人 核心结论 版本记录 监测SKU").split(" "));
export function projectDetail(data: DetailProjection, doc: Document): DocumentFragment {
  const template = doc.createElement("template");
  template.innerHTML = screenMarkup(detailScreens[data.kind][0]);
  const body = template.content.querySelector(".modal-body,.kpm-body,.rival-evidence-body");
  const result = doc.createDocumentFragment();
  if (body) {
    // Local templates also power sample debugging. Start from empty data slots
    // before inserting any authenticated values, even on a partial response.
    body.querySelectorAll("script,style,svg,img,button,input,select,textarea,[contenteditable],tbody tr,.data-source-footer,.report-ai-assistant").forEach(el => el.remove());
    for (const el of [body,...body.querySelectorAll("*")]) {
      for (const a of Array.from(el.attributes)) if (a.name.startsWith("on") || ["href","src","style","title"].includes(a.name)) el.removeAttribute(a.name);
      for (const child of Array.from(el.childNodes)) {
        if (child.nodeType===3 && !fixed.has((child.textContent || "").trim())) child.textContent = "";
      }
    }
    const mapping = fields[data.kind] || {};
    for (const [key,id] of Object.entries(mapping)) {
      const target = body.querySelector("#"+id);
      if (!target) continue;
      target.replaceChildren();
      const table = data.tables[key];
      if (table) {
        const tbl = doc.createElement("table");
        const head = tbl.createTHead().insertRow();
        table.columns.forEach(col => {const th=doc.createElement("th");th.textContent=col;head.append(th);});
        const rows = target.tagName==="TBODY" ? target as HTMLTableSectionElement : tbl.createTBody();
        table.rows.forEach(values => {const row=rows.insertRow();values.forEach(v=>row.insertCell().textContent=displayValue(v));});
        if (rows!==target) target.append(tbl);
      } else if (data.lists[key]) {
        data.lists[key].forEach(value=>{const item=doc.createElement("span");item.className="sell-point";item.textContent=value;target.append(item);});
      } else {
        target.textContent = displayValue(data.values[key]);
        if (key==="level") (target as HTMLElement).dataset.level = target.textContent;
      }
    }
    result.append(...Array.from(body.childNodes));
  }
  return result;
}
