import { useState, type ReactNode } from "react";
import Modal from "@douyinfe/semi-ui/lib/es/modal";
import Table from "@douyinfe/semi-ui/lib/es/table";
import IconArrowRight from "@douyinfe/semi-icons/lib/es/icons/IconArrowRight";
import IconBulb from "@douyinfe/semi-icons/lib/es/icons/IconBulb";
import IconChevronRight from "@douyinfe/semi-icons/lib/es/icons/IconChevronRight";
import { displayValue, type Action, type Chart, type DataTable, type Evidence, type Page, type Row, type View } from "./contract";

export function Dialog({title, close, children}: {title: string; close: () => void; children: ReactNode}) {
  return <Modal visible title={title} footer={null} onCancel={close} width="min(540px, 94vw)"
    className="gtm-modal" getPopupContainer={() => document.querySelector<HTMLElement>(".gtm") ?? document.body}>
    <div className="gtm-dialog">{children}</div></Modal>;
}
export function Sources({items}: {items: Evidence[]}) {
  return <div className="gtm-sources"><h3>数据依据</h3>{items.length ? items.map(item =>
    <article key={item.evidence_id}><strong>{item.source}</strong><small>{item.observed_at || "时间未知"} · {item.evidence_id}</small>
      <p>{item.excerpt}</p>{item.source_file_id && <small>来源文件 {item.source_file_id}　原始行 {item.raw_row_id || "—"}</small>}
      {item.evidence_url?.startsWith("/api/gtm/") && <a href={item.evidence_url} target="_blank" rel="noreferrer">查看原始凭证</a>}</article>
  ) : <p>暂无可追溯证据</p>}</div>;
}

function Plot({chart}: {chart: Chart}) {
  const colors = ["var(--semi-color-primary)", "var(--semi-color-warning)", "var(--semi-color-danger)", "var(--semi-color-success)", "rgb(var(--semi-violet-5))"];
  const known = chart.points.filter(p => p.value !== null);
  if (!known.length) return <p className="gtm-empty">当前范围暂无观测值</p>;
  if (chart.kind === "distribution") {
    const total = known.reduce((n, p) => n + Math.max(0, p.value!), 0);
    let end = 0;
    const segments = chart.points.map((p, i) => {
      const start = end;
      end += total ? Math.max(0, p.value ?? 0) / total * 100 : 0;
      return `${colors[i % colors.length]} ${start}% ${end}%`;
    });
    return <div className="gtm-distribution"><div className="gtm-ring" style={{background: total ? `conic-gradient(${segments.join(",")})` : "#e9eef0"}}>
      <div><b>{known.length === chart.points.length ? displayValue(total) : "—"}</b><small>{chart.unit}</small></div></div>
      <ul>{chart.points.map((p, i) => <li key={i}><i style={{background: colors[i % colors.length]}}/>{p.label}<b>{displayValue(p.value, chart.unit)}</b></li>)}</ul></div>;
  }
  const max = Math.max(1, ...known.map(p => p.value!));
  const min = Math.min(0, ...known.map(p => p.value!));
  const x = (i: number) => 48 + i * 392 / Math.max(1, chart.points.length - 1);
  const y = (v: number) => 142 - (v - min) / (max - min) * 112;
  const intervals = known.every(p => Number.isInteger(p.value)) ? Math.min(4, max - min) : 4;
  const ticks = Array.from({length: intervals + 1}, (_, i) => {
    const v = max - i * (max - min) / intervals;
    return known.every(p => Number.isInteger(p.value)) ? Math.round(v) : Number(v.toFixed(2));
  });
  let path = "";
  chart.points.forEach((p, i) => {
    if (p.value !== null) path += `${i && chart.points[i - 1].value !== null ? "L" : "M"}${x(i)} ${y(p.value)} `;
  });
  return <svg className="gtm-line-chart" viewBox="0 0 468 172" role="img" aria-label={chart.title}>
    <title>{chart.points.map(p => p.label + " " + displayValue(p.value, chart.unit)).join("、")}</title>
    {ticks.map(v => <g key={v}><line x1="48" x2="444" y1={y(v)} y2={y(v)}/>
      <text x="39" y={y(v) + 4} textAnchor="end">{v}</text></g>)}
    <path d={path} fill="none" stroke="var(--semi-color-primary)" strokeWidth="2.5" strokeLinejoin="round"/>
    {chart.points.map((p, i) => <g key={i}>{p.value !== null && <circle cx={x(i)} cy={y(p.value)} r="3" fill="var(--semi-color-primary)"><title>{p.label} · {displayValue(p.value, chart.unit)}</title></circle>}
      {(i % Math.ceil(chart.points.length / 7) === 0 || i === chart.points.length - 1) && <text x={x(i)} y="163" textAnchor="middle">{p.label}</text>}</g>)}
  </svg>;
}

function Results({table, open, navigate, pageIndex, pageSize, paginate}: {
  table: DataTable; open: (row: Row) => void; navigate: (page: Page) => void;
  pageIndex: number; pageSize: number; paginate?: (page: number) => void;
}) {
  return <section className="gtm-panel"><header><h2>{table.title}</h2>
    {table.target && <button onClick={() => navigate(table.target!)}>查看全部 <IconChevronRight/></button>}</header>
    <div className="gtm-table-scroll"><Table<Row> rowKey="id" size="small" pagination={false} dataSource={table.rows}
      empty={<p className="gtm-empty">当前筛选范围暂无记录</p>} columns={[
        ...table.columns.map(c => ({title:c.label, key:c.key, render: (_:unknown, row:Row) => displayValue(row.cells[c.key], c.unit)})),
        {title:"操作", key:"action", render: (_:unknown,row:Row) => <button className="gtm-link" onClick={() => open(row)}>查看</button>}
      ]}/></div>
    {paginate && <footer>共 {table.total.toLocaleString()} 条 <span/><button disabled={pageIndex === 0} onClick={() => paginate(pageIndex - 1)}>上一页</button>
      {pageIndex + 1} / {Math.max(1, Math.ceil(table.total / pageSize))}<button disabled={(pageIndex + 1) * pageSize >= table.total} onClick={() => paginate(pageIndex + 1)}>下一页</button></footer>}
  </section>;
}

export function BusinessView({data, navigate, ask, act, refresh, offset, limit, setOffset}: {
  data: View; navigate: (page: Page) => void; ask: (q: string) => void; act: (action: Action, row: Row | null) => void;
  refresh: () => void; offset: number; limit: number; setOffset: (value: number) => void;
}) {
  const [selected, setSelected] = useState<Row | null>(null);
  const [sources, setSources] = useState<Evidence[] | null>(null);
  return <>
    {data.notice && <p className="gtm-notice" role="status">{data.notice}</p>}
    {data.insights.length > 0 && <section className="gtm-summary">
      <header><span className="gtm-ai">AI</span><h2>{data.page === "daily" ? "工作总览" : "分析总结与建议"}</h2><small>{data.as_of && "数据截至 " + data.as_of.replace("T", " ").slice(0, 16)}</small>
        <button onClick={refresh}>刷新总览</button></header>
      <div className="gtm-summary-grid">{data.insights.map(item => <article className={"gtm-insight " + item.tone} key={item.title}>
        <h3><span>{item.label}</span>{item.title}</h3><p>{item.body}</p>
        {item.bullets.length > 0 && <ul>{item.bullets.map(b => <li key={b}>{b}</li>)}</ul>}
        {item.evidence.length > 0 && <button className="gtm-link" onClick={() => setSources(item.evidence)}>查看依据</button>}</article>)}</div>
      {data.insights.some(i => i.question) && <><p className="gtm-follow"><IconBulb/> 我可以继续帮你</p><div className="gtm-chips">
        {data.insights.filter(i => i.question).map(i => <button key={i.title} onClick={() => ask(i.question!)}>{i.question} <IconArrowRight/></button>)}</div></>}
    </section>}
    {data.metrics.length > 0 && <section className="gtm-panel"><header><h2>核心指标</h2><small>当前筛选范围</small></header>
      <div className="gtm-metrics">{data.metrics.map(m => <div key={m.label} className={"gtm-metric " + (m.tone || "")}>
        <div>{m.label}{m.target && <button className="gtm-link" onClick={() => navigate(m.target!)}>详情 ›</button>}</div><strong>{displayValue(m.value)}<em>{m.unit}</em></strong><small>{m.hint}</small>
        {m.basis && <details><summary>统计口径</summary><small>{m.basis.grain} · {m.basis.population}<br/>{m.basis.coverage_from} 至 {m.basis.coverage_to}<br/>批次 {m.basis.source_batch} · 同步 {m.basis.synced_at || "未知"}</small></details>}</div>)}</div></section>}
    {data.charts.length > 0 && <section className="gtm-panel"><header><h2>{data.page === "daily" ? "价格违规概览" : "趋势与分布"}</h2></header>
      <div className="gtm-plots">{data.charts.map(chart => <article key={chart.title}><h3>{chart.title}</h3><Plot chart={chart}/></article>)}</div></section>}
    {data.tables.map((table, index) => <Results key={table.id} table={table} open={setSelected} navigate={navigate}
      pageIndex={Math.floor(offset / limit)} pageSize={limit} paginate={data.page !== "daily" && index === 0 ? n => setOffset(n * limit) : undefined}/>)}
    {!data.tables.length && !data.insights.length && !data.metrics.length && !data.charts.length && <p className="gtm-empty">当前范围暂无业务数据</p>}
    <small className="gtm-snapshot">数据快照 {data.snapshot_id}{data.method_version && " · 方法 " + data.method_version}{data.review_status && " · " + data.review_status}{data.confidence != null && " · 置信度 " + displayValue(data.confidence)}</small>
    {selected && <Dialog title={selected.title} close={() => setSelected(null)}>
      <dl>{selected.detail.map((field, i) => <div key={i}><dt>{field.label}</dt><dd>{displayValue(field.value)}</dd></div>)}</dl><Sources items={selected.evidence}/>
      {selected.actions.length > 0 && <footer>{selected.actions.map(a => <button className="primary" key={a.operation} onClick={() => {act(a, selected); setSelected(null);}}>{a.label}</button>)}</footer>}</Dialog>}
    {sources && <Dialog title="分析依据" close={() => setSources(null)}><Sources items={sources}/></Dialog>}
  </>;
}
