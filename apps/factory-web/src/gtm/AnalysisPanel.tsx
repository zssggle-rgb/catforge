import { useState } from "react";
import type { DataTable, Row } from "./contract";
import { displayValue } from "./contract";

export function AnalysisPanel({tab, table, open}: {tab:string;table:DataTable;open:(row:Row)=>void}) {
  const [selected,setSelected] = useState(0);
  const {columns,rows} = table;
  const field = (r:Row, i:number) => columns[i] ? displayValue(r.cells[columns[i].key],columns[i].unit) : "—";
  if (!rows.length) return <section className="gtm-panel"><h2>{table.title}</h2><p className="gtm-empty">当前范围暂无分析记录</p></section>;
  if (tab==="product") return <section className="gtm-panel"><header><h2>{table.title}</h2></header><div className="gtm-matrix-scroll">
    <table className="gtm-matrix"><thead><tr><th>产品参数</th>{rows.map(r=><th key={r.id}><button className="gtm-link" onClick={()=>open(r)}>{field(r,0)}</button></th>)}</tr></thead>
      <tbody>{columns.slice(1).map((c,i)=><tr key={c.key}><th>{c.label}</th>{rows.map(r=><td key={r.id}>{field(r,i+1)}</td>)}</tr>)}</tbody></table></div></section>;
  if (tab==="weight") {
    const r=rows[Math.min(rows.length-1,selected)];
    return <section className="gtm-panel"><header><h2>{table.title}</h2><select aria-label="选择卖点" value={selected}
      onChange={e=>setSelected(Number(e.target.value))}>{rows.map((item,i)=><option value={i} key={item.id}>{field(item,1)}</option>)}</select></header>
      <div className="gtm-metrics">{columns.map((c,i)=><div className="gtm-metric" key={c.key}><small>{c.label}</small><b>{field(r,i)}</b></div>)}</div>
      <button className="gtm-link" onClick={()=>open(r)}>查看估值依据</button></section>;
  }
  return <section className={"gtm-panel gtm-analysis-"+tab}><header><h2>{table.title}</h2></header><div className="gtm-detail-cards">
    {rows.map(r=><article key={r.id}><h3>{field(r,0)}</h3><dl>{columns.slice(1).map((c,i)=><div key={c.key}><dt>{c.label}</dt><dd>{field(r,i+1)}</dd></div>)}</dl>
      <button className="gtm-link" onClick={()=>open(r)}>{tab==="voc"?"查看评论依据":tab==="price-volume"?"查看量价依据":"查看明细"}</button></article>)}
    </div></section>;
}
