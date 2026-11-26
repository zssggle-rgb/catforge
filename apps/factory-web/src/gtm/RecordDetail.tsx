import { useState } from "react";
import { displayValue, type Action, type Cell, type Row } from "./contract";
import { Dialog, Sources } from "./DetailDialog";
import { productName } from "./brand";

type Group = {title: string; keys: string[]};
// The detail pages use their own business vocabulary. Unknown fields, evidence
// and newly supplied columns remain reachable even with an older server.
const groups: Record<string, Group[]> = {
  "own-monitor": [
    {title:"巡检对象", keys:["型号","渠道","店铺名称","观测日期"]},
    {title:"价格证据链", keys:["到手价（元）","月度底价（元）","价差（元）","预警等级","处理状态"]}
  ],
  "rival-monitor": [
    {title:"调价对象", keys:["型号","渠道","店铺名称","观测日期"]},
    {title:"历史价格对比", keys:["上次到手价（元）","到手价（元）","调价（元）"]}
  ],
  launch: [
    {title:"产品信息", keys:["品牌","型号","核心规格"]},
    {title:"上市表现", keys:["上市日期","渠道","首发价（元）"]}
  ],
  "todo-center": [
    {title:"任务详情", keys:["任务标题","类型","优先级","状态","截止时间","负责人"]},
  ],
  reports: [
    {title:"报告信息", keys:["报告名称","品类","周期","状态","订阅","更新时间"]},
    {title:"报告正文", keys:["正文"]}
  ],
  "key-model": [
    {title:"重点产品", keys:["型号","品牌","核心分类"]},
    {title:"销售表现", keys:["sales_volume_units","sales_amount_yuan","avg_price_yuan"]}
  ]
};
const titles: Record<string,string> = {"own-monitor":"价格异常证据链","rival-monitor":"竞品调价详情",
  launch:"竞品百科","todo-center":"待办任务详情",reports:"订阅报告","key-model":"重点产品表现"};
const fieldNames: Record<string,string> = {sales_volume_units:"销量（台）",sales_amount_yuan:"销额（元）",avg_price_yuan:"均价（元）"};
export function RecordDetail({table, row, close, act}: {
  table: string; row: Row; close: () => void; act: (a: Action, row: Row) => void;
}) {
  const [tab, setTab] = useState("record");
  const fields: Record<string,Cell> = {...row.cells, ...Object.fromEntries(row.detail.map(f => [f.label,f.value]))};
  const sections = (groups[table] || []).map(g => ({...g, keys:g.keys.filter(k => k in fields)})).filter(g => g.keys.length);
  const used = new Set(sections.flatMap(g => g.keys));
  const extra = Object.keys(fields).filter(k => !used.has(k));
  if (extra.length) sections.push({title:"明细", keys:extra});
  return <Dialog title={titles[table] || row.title} close={close}><div className="gtm-record-detail">
    {table === "reports" && <div className="hunter-letterhead" role="img" aria-label={productName}/>}
    <h2>{row.title}</h2>
    <div className="gtm-tabs"><button aria-pressed={tab==="record"} onClick={() => setTab("record")}>业务详情</button>
      <button aria-pressed={tab==="evidence"} onClick={() => setTab("evidence")}>原始证据（{row.evidence.length}）</button></div>
    {tab === "record" ? sections.map(g => <section key={g.title}><h3>{g.title}</h3>
      {g.title === "报告正文" ? <article>{displayValue(fields["正文"])}</article> :
        <dl>{g.keys.map(k => <div key={k}><dt>{fieldNames[k] || k}</dt><dd>{displayValue(fields[k])}</dd></div>)}</dl>}</section>) : <Sources items={row.evidence}/>}
    {row.actions.length > 0 && <footer>{row.actions.map(a => <button className="primary" key={a.operation} onClick={() => act(a,row)}>{a.label}</button>)}</footer>}
  </div></Dialog>;
}
