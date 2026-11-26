import { useEffect, useRef, useState, type ReactNode } from "react";
import "@douyinfe/semi-ui/react19-adapter";
import "@douyinfe/semi-ui/lib/es/_base/base.css";
import Button from "@douyinfe/semi-ui/lib/es/button";
import Select from "@douyinfe/semi-ui/lib/es/select";
import IconHistogram from "@douyinfe/semi-icons/lib/es/icons/IconHistogram";
import IconBell from "@douyinfe/semi-icons/lib/es/icons/IconBell";
import IconBulb from "@douyinfe/semi-icons/lib/es/icons/IconBulb";
import IconCalendar from "@douyinfe/semi-icons/lib/es/icons/IconCalendar";
import IconCheckList from "@douyinfe/semi-icons/lib/es/icons/IconCheckList";
import IconDownload from "@douyinfe/semi-icons/lib/es/icons/IconDownload";
import IconEyeOpened from "@douyinfe/semi-icons/lib/es/icons/IconEyeOpened";
import IconArticle from "@douyinfe/semi-icons/lib/es/icons/IconArticle";
import IconLineChartStroked from "@douyinfe/semi-icons/lib/es/icons/IconLineChartStroked";
import IconMenu from "@douyinfe/semi-icons/lib/es/icons/IconMenu";
import IconPlus from "@douyinfe/semi-icons/lib/es/icons/IconPlus";
import IconRefresh from "@douyinfe/semi-icons/lib/es/icons/IconRefresh";
import IconSearch from "@douyinfe/semi-icons/lib/es/icons/IconSearch";
import IconSend from "@douyinfe/semi-icons/lib/es/icons/IconSend";
import { BusinessView, Dialog, Sources } from "./BusinessView";
import { gtm } from "./client";
import { defaultFilters, displayValue, pages, pageTabs, readRoute, type Action, type Choice, type Context,
  type Attachment, type Conversation, type FacetKey, type Filters, type Origin, type Page, type Route, type Row, type Scope, type Selection, type View, type Workspace } from "./contract";
import "./gtm.css";

const titles = {...pages, chat: "新建对话", history: "历史记录", help: "帮助中心"};
const icons: Record<Page, ReactNode> = {
  daily: <IconCalendar/>, "key-model": <IconHistogram/>, "own-monitor": <IconSearch/>,
  launch: <IconBell/>, "rival-monitor": <IconEyeOpened/>, competitor: <IconBulb/>,
  premium: <IconLineChartStroked/>, "todo-center": <IconCheckList/>, reports: <IconArticle/>
};
type Load<T> = {key: string; data?: T; error?: string};
function useRead<T>(key: string, fetcher: (signal: AbortSignal) => Promise<T>) {
  const [result, setResult] = useState<Load<T>>({key: ""});
  const loader = useRef(fetcher);
  loader.current = fetcher;
  useEffect(() => {
    if (!key) return;
    const controller = new AbortController();
    loader.current(controller.signal).then(data => {
      if (!controller.signal.aborted) setResult({key, data});
    }).catch((e: Error) => {
      if (!controller.signal.aborted) setResult({key, error: e.message || "读取失败"});
    });
    return () => controller.abort();
  }, [key]);
  return result.key === key ? result : {key};
}
function Status({error, retry}: {error?: string; retry: () => void}) {
  return <div className="gtm-state" role="status">{error || "正在读取…"}{error && <button onClick={retry}>重试</button>}</div>;
}
function exportView(view: View) {
  const lines = [pages[view.page], view.as_of || "", view.project_id + " · " + view.category_code + " · " + view.snapshot_id, view.notice || "",
    ...view.insights.flatMap(i => [i.title, i.body, ...i.bullets, ...i.evidence.map(e => e.source + " · " + e.evidence_id)]),
    ...view.metrics.map(m => m.label + "　" + displayValue(m.value, m.unit)),
    ...view.tables.flatMap(t => [t.title, t.columns.map(c => c.label).join("\t"),
      ...t.rows.map(row => t.columns.map(c => displayValue(row.cells[c.key], c.unit)).join("\t"))])];
  const url = URL.createObjectURL(new Blob([lines.join("\n")], {type: "text/plain;charset=utf-8"}));
  const a = document.createElement("a"); a.href = url; a.download = "GTM-" + pages[view.page] + ".txt"; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function FilterSelect({label, value, items, change}: {label: string; value: string; items: Choice[]; change: (value: string) => void}) {
  const id = "gtm-filter-" + label;
  return <div className="gtm-filter-select"><span id={id}>{label}</span><Select aria-labelledby={id} value={value}
    optionList={items.map(item => ({value: item.id, label: item.label}))} onSelect={v => change(String(v))}/></div>;
}
function FilterBar({project, filters, apply, showQuery}: {project: Workspace; filters: Filters; apply: (v: Filters) => void; showQuery: boolean}) {
  const [draft, setDraft] = useState(filters);
  const set = <K extends keyof Filters>(key: K, value: Filters[K]) => setDraft(v => ({...v, [key]: value}));
  return <form className="gtm-filters" onSubmit={e => {e.preventDefault(); apply(draft);}}>
    <FilterSelect label="渠道" value={draft.channel} items={[{id:"",label:"全渠道"}, ...project.channels]} change={v => set("channel",v)}/>
    <FilterSelect label="品类" value={draft.category_code} items={project.categories} change={v => setDraft({...draft, category_code:v, subcategory:""})}/>
    <FilterSelect label="品类细分" value={draft.subcategory} items={[{id:"",label:"全部"}, ...(project.categories.find(c => c.id === draft.category_code)?.subcategories || [])]} change={v => set("subcategory",v)}/>
    <FilterSelect label="时间周期" value={draft.period} items={[{id:"today",label:"今日"},{id:"yesterday",label:"昨日"},{id:"7d",label:"近7天"},{id:"30d",label:"近30天"},{id:"custom",label:"自定义"}]} change={v => setDraft({...draft,period:v as Filters["period"],date_from:"",date_to:""})}/>
    {draft.period === "custom" && <><input aria-label="起始日期" type="date" required value={draft.date_from} max={draft.date_to || undefined} onChange={e => set("date_from", e.target.value)}/>
      <input aria-label="结束日期" type="date" required value={draft.date_to} min={draft.date_from} onChange={e => set("date_to", e.target.value)}/></>}
    {showQuery && <input aria-label="搜索型号或关键词" placeholder="型号或关键词" value={draft.query} onChange={e => set("query", e.target.value)}/>}
    <Button htmlType="submit" theme="solid">查询</Button></form>;
}
const options = (list: Choice[]) => list.map(o => <option key={o.id} value={o.id}>{o.label}</option>);
const emptySelection: Selection = {model_id: "", competitor_ids: [], brand_ids: []};

function AnalysisScope({project, category, page, value, change}: {project: string; category: string; page: Page; value: Selection; change: (s: Selection) => void}) {
  const [search, setSearch] = useState("");
  const [retry, setRetry] = useState(0);
  const brand = page === "premium";
  const max = page === "rival-monitor" ? 5 : 10;
  const key = [project, category, page, retry].join(":");
  const own = useRead(brand ? "" : key, sig => gtm.choices(project, category, "own-model", "", sig));
  const others = useRead(key + search, sig => gtm.choices(project, category, brand ? "brand" : "competitor", search, sig));
  const [names, setNames] = useState<Record<string, string>>({});
  const picked = brand ? value.brand_ids : value.competitor_ids;
  function toggle(id: string) {
    const ids = picked.includes(id) ? picked.filter(i => i !== id) : [...picked, id];
    if (ids.length <= max) change({...value, [brand ? "brand_ids" : "competitor_ids"]: ids});
  }
  return <section className="gtm-analysis-scope"><div>{!brand && <label>我品型号 <select aria-label="我品型号" value={value.model_id}
    onChange={e => change({...value, model_id: e.target.value, competitor_ids: []})}><option value="">全部授权型号</option>{options(own.data || [])}</select></label>}
    <label>{brand ? "对比品牌" : "竞品型号"} <input aria-label="检索候选" placeholder={brand ? "查找品牌" : "查找竞品"} value={search} onChange={e => setSearch(e.target.value)}/></label>
    <select aria-label={brand ? "添加品牌" : "添加竞品"} value="" disabled={picked.length >= max} onChange={e => {
      const id = e.target.value; setNames({...names, [id]: others.data?.find(o => o.id === id)?.label || id}); toggle(id);
    }}><option value="">添加{brand ? "品牌" : "竞品"}</option>{options((others.data || []).filter(o => !picked.includes(o.id)))}</select></div>
    {picked.length > 0 && <div className="gtm-chips">{picked.map(id => <button key={id} aria-label={"移除 " + (names[id] || id)} onClick={() => toggle(id)}>{names[id] || id} ×</button>)}</div>}
    {(own.error || others.error) && <Status error={own.error || others.error} retry={() => setRetry(n => n + 1)}/>}</section>;
}
const navigate = (route: Route, id = "") => {window.location.hash = "/" + route + (id ? "/" + encodeURIComponent(id) : "");};

function Chat({project, filters, id, seed, origin, updateHistory}: {project: string; filters: Filters; id: string; seed: string; origin: Origin | null; updateHistory: () => void}) {
  const [question, setQuestion] = useState(seed);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const [latest, setLatest] = useState<Conversation>();
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const mounted = useRef(true);
  const attempt = useRef({text: "", key: ""});
  useEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  const chat = useRead(id ? id + ":" + reload : "", signal => gtm.conversation(project, filters.category_code, id, signal));
  const current = latest ?? chat.data;
  async function send() {
    const text = question.trim();
    if (!text || busy) return;
    setError(""); setBusy(true);
    const signature = JSON.stringify([text, attachments.map(a => a.id)]);
    if (attempt.current.text !== signature) attempt.current = {text: signature, key: crypto.randomUUID()};
    try {
      const response = await gtm.ask(project, filters, id || null, text, attempt.current.key, id ? null : origin, attachments.map(a => a.id));
      if (!mounted.current) return;
      setLatest(response); setQuestion(""); setAttachments([]); attempt.current = {text: "", key: ""}; updateHistory();
      if (!id) navigate("chat", response.id);
    } catch (e) {if (mounted.current) setError((e as Error).message);}
    finally {if (mounted.current) setBusy(false);}
  }
  if (id && !current) return <Status error={chat.error} retry={() => setReload(v => v + 1)}/>;
  return <section className="gtm-chat"><h2>{current?.label || "想分析什么经营问题？"}</h2>
    {current?.messages.map((m, i) => <article className={m.role} key={i}><b>{m.role === "user" ? "我的问题" : "GTM 助手"}</b><p>{m.text}</p>
      {m.evidence.length > 0 && <details><summary>查看依据</summary><Sources items={m.evidence}/></details>}</article>)}
    <label className="gtm-upload">添加附件 <input type="file" aria-label="对话附件" disabled={busy} accept=".csv,.xlsx,.pdf,.txt,.png,.jpg,.jpeg" onChange={async e => {
      const file = e.target.files?.[0]; e.target.value = ""; if (!file) return;
      setBusy(true);setError("");try {const item = await gtm.attach(project, filters.category_code, file, "chat");setAttachments(a => [...a, item]);}
      catch (err) {setError((err as Error).message);} finally {setBusy(false);}
    }}/></label>{attachments.map(a => <button type="button" key={a.id} disabled={busy} onClick={() => setAttachments(v => v.filter(x => x.id !== a.id))}>{a.name} ×</button>)}
    <form onSubmit={e => {e.preventDefault(); void send();}}><textarea aria-label="分析问题" placeholder="输入型号、竞品或价格问题…" value={question} onChange={e => setQuestion(e.target.value)} required maxLength={4000}/>
      <button className="primary" disabled={busy || !question.trim()}><IconSend/> {busy ? "发送中" : "发送"}</button></form>{error && <p role="alert">{error}</p>}</section>;
}

function ConfirmAction({action, row, scope, snapshot, close, done}: {action: Action; row: Row | null; scope: Scope; snapshot: string; close: () => void; done: (msg: string) => void}) {
  const [input, setInput] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [fields, setFields] = useState<Record<string,string>>(() => Object.fromEntries((action.fields || []).map(f => [f.key, f.value ?? ""])));
  const update = (name: string, value: string) => {setFields(f => ({...f, [name]: value}));setKey(crypto.randomUUID());};
  const needsInput = action.operation === "create-report" || action.operation === "set-key-models";
  return <Dialog title={action.label} close={() => {if (!busy) close();}}><form onSubmit={async e => {
    e.preventDefault(); if (busy) return; setBusy(true); setError("");
    try {const receipt = await gtm.act(scope, action.operation, row?.id ?? null, input.trim(), key, snapshot, fields); done(receipt.message);}
    catch (err) {setError((err as Error).message); setBusy(false);}
  }}>
    {row && <p>{row.title}</p>}{needsInput && <label>{action.operation === "create-report" ? "报告名称" : "重点型号（以逗号分隔）"}
      <input required value={input} maxLength={500} disabled={busy} onChange={e => {setInput(e.target.value);setKey(crypto.randomUUID());}}/></label>}
    {action.fields?.map(f => <label key={f.key}>{f.label}{f.kind === "file" ? <input type="file" accept=".xlsx,.csv" disabled={busy} required={f.required && !fields[f.key]} onChange={async e => {
      const file = e.target.files?.[0]; update(f.key, ""); if (!file) return; setBusy(true);setError("");
      try {update(f.key,(await gtm.attach(scope.project_id, scope.category_code, file, "floor")).id);}
      catch(err){setError((err as Error).message);} finally {setBusy(false);}
    }}/> : f.kind === "textarea" ? <textarea required={f.required} value={fields[f.key]} disabled={busy} onChange={e => update(f.key,e.target.value)}/>
      : <input type={f.kind} required={f.required} value={fields[f.key]} disabled={busy} onChange={e => update(f.key,e.target.value)}/>}</label>)}
    {error && <p role="alert">{error}</p>}<footer><button type="button" disabled={busy} onClick={close}>取消</button>
      <button className="primary" disabled={busy || (needsInput && !input.trim())}>{busy ? "提交中" : "确认"}</button></footer></form></Dialog>;
}

export default function GtmApp() {
  const [reload, setReload] = useState(0);
  const context = useRead("context:" + reload, gtm.context);
  const [projectId, setProjectId] = useState("");
  const project = context.data?.projects.find(p => p.id === projectId) ?? context.data?.projects[0];
  if (!context.data || !project || !project.categories.length) return <main className="gtm gtm-boot"><h1>GTM竞价策略助手</h1>
    <Status error={context.error || (context.data ? "当前账号暂无可用品类或项目" : undefined)} retry={() => setReload(v => v + 1)}/>
    <p><a href="/core3">三竞品研判台</a>　<a href="/factory">品类资产工作台</a></p></main>;
  return <WorkspaceApp key={project.id} project={project} context={context.data} changeProject={id => {navigate("daily"); setProjectId(id);}}/>;
}
function WorkspaceApp({context, project, changeProject}: {context: Context; project: Workspace; changeProject: (id: string) => void}) {
  const [location, setLocation] = useState(() => readRoute(window.location.hash));
  const {route, conversation} = location;
  const page = Object.hasOwn(pages, route) ? route as Page : undefined;
  const [filters, setFilters] = useState(() => defaultFilters(project.categories[0].id));
  const [selection, setSelection] = useState<Selection>(emptySelection);
  const [facets, setFacets] = useState<Partial<Record<FacetKey, string>>>({});
  const [tabKey, setTabKey] = useState("");
  const tabs = page ? pageTabs[page] : undefined;
  const tab = tabs?.find(t => t[0] === tabKey)?.[0] ?? tabs?.[0][0] ?? "";
  const [offset, setOffset] = useState(0); const [revision, setRevision] = useState(0);
  const [historyRev, setHistoryRev] = useState(0);
  const [sidebar, setSidebar] = useState(false); const [seed, setSeed] = useState(""); const [chatKey, setChatKey] = useState(0);
  const [origin, setOrigin] = useState<Origin | null>(null);
  const [action, setAction] = useState<{action: Action; row: Row | null} | null>(null);
  const [message, setMessage] = useState("");
  const main = useRef<HTMLElement>(null);
  useEffect(() => {
    const change = () => {setLocation(readRoute(window.location.hash)); setTabKey(""); setFacets({}); setSelection(emptySelection); setOffset(0); setSidebar(false); setAction(null); setMessage(""); main.current?.scrollTo(0, 0);};
    window.addEventListener("hashchange", change); return () => window.removeEventListener("hashchange", change);
  }, []);
  useEffect(() => {document.title = titles[route] + " · GTM竞价策略助手";}, [route]);
  const scope: Scope = {...filters, query: page === "daily" ? "" : filters.query, project_id: project.id, page: page ?? "daily", tab, offset, limit: 20};
  const hasSelection = page === "competitor" || page === "rival-monitor" || page === "premium";
  const viewScope = {...scope, ...facets, ...(hasSelection ? (page === "premium" ? {brand_ids: selection.brand_ids} : {model_id: selection.model_id, competitor_ids: selection.competitor_ids}) : {})};
  const viewKey = page ? JSON.stringify([viewScope, revision]) : "";
  const result = useRead(viewKey, signal => gtm.view(viewScope, signal));
  const history = useRead(project.id + ":" + filters.category_code + ":" + historyRev, signal => gtm.history(project.id, filters.category_code, signal));
  const refresh = () => setRevision(r => r + 1);
  const startChat = (q = "") => {setSeed(q); setOrigin(q && page && result.data ? {page, tab, snapshot_id: result.data.snapshot_id, scope:viewScope} : null); setChatKey(n => n + 1); setSidebar(false); navigate("chat");};
  return <div className="gtm">
    {sidebar && <button className="gtm-backdrop" aria-label="关闭菜单" onClick={() => setSidebar(false)}/>}
    <aside className={"gtm-sidebar" + (sidebar ? " open" : "")}><div className="gtm-brand"><i><IconHistogram/></i><div><b>GTM竞价策略助手</b><small>CatForge · 智能决策工作台</small></div></div>
      <button className="gtm-new primary" onClick={() => startChat()}><IconPlus/> 新建对话</button>
      <div className="gtm-side-scroll"><nav>{(Object.keys(pages) as Page[]).map(p => <a key={p} href={"#/" + p} aria-current={route === p ? "page" : undefined}
        className={["launch", "todo-center"].includes(p) ? "gtm-divider" : ""}>{icons[p]}{pages[p]}</a>)}</nav>
      <div className="gtm-history"><header>最近对话 <a href="#/history">查看更多</a></header>
        {history.data?.slice(0, 5).map(h => <a key={h.id} href={"#/chat/" + encodeURIComponent(h.id)}>{h.label}</a>)}
        {!history.data?.length && <small>{history.error ? "对话暂不可用" : "暂无最近对话"}</small>}</div></div>
      <div className="gtm-profile"><i>{context.user.name.slice(0, 1)}</i><div><b>{context.user.name}</b><small>{context.user.role}</small></div>
        {context.projects.length > 1 ? <select aria-label="切换项目" value={project.id} onChange={e => changeProject(e.target.value)}>{options(context.projects)}</select> : <span>{project.label}</span>}</div>
    </aside><div className="gtm-main"><header className="gtm-top"><button className="gtm-menu" aria-label="打开菜单" onClick={() => setSidebar(true)}><IconMenu/></button>
      <span>GTM竞价策略助手 / <b>{titles[route]}</b></span>{context.mode === "sample" && <small>样例数据</small>}<a href="#/help">帮助</a></header>
      <main ref={main} className="gtm-work"><header className="gtm-heading"><h1>{titles[route]}</h1>
        {result.data?.as_of && <time>{result.data.as_of.slice(0, 10)}</time>}
        {page && <div className="gtm-tools">{result.data && <button className="primary" onClick={() => exportView(result.data!)}><IconDownload/> {page === "daily" ? "日报导出" : "导出当前页"}</button>}
          {result.data?.actions.map(a => <button key={a.operation} onClick={() => setAction({action: a, row: null})}>{a.label}</button>)}<button onClick={refresh}><IconRefresh/> 刷新</button></div>}</header>
        {page && <><FilterBar key={route + filters.category_code} project={project} filters={filters} showQuery={page !== "daily"} apply={f => {if (f.category_code !== filters.category_code) {setSelection(emptySelection);setFacets({});} setFilters(f); setOffset(0); refresh();}}/>
          {!!result.data?.facets?.length && <div className="gtm-filters">{result.data.facets.map(f => <label key={f.key}>{f.label}<select value={facets[f.key] || ""} onChange={e => {setFacets({...facets,[f.key]:e.target.value});setOffset(0);}}><option value="">全部</option>{options(f.options)}</select></label>)}</div>}
          {hasSelection && <AnalysisScope key={page + filters.category_code} project={project.id} category={filters.category_code} page={page} value={selection} change={s => {setSelection(s);setOffset(0);}}/>}
          {tabs && <div className="gtm-tabs" aria-label={titles[route]}>{tabs.map(([k, label]) => <button key={k} aria-pressed={tab === k} onClick={() => {setTabKey(k);setOffset(0);}}>{label}</button>)}</div>}
          {message && <p role="status" className="gtm-notice">{message}</p>}{result.data ? <BusinessView key={viewKey} data={result.data} navigate={navigate} ask={startChat}
            act={(a, row) => setAction({action: a, row})} refresh={refresh} offset={offset} limit={scope.limit} setOffset={setOffset}/> : <Status error={result.error} retry={refresh}/>}</>}
        {route === "chat" && <Chat key={[filters.category_code, conversation, chatKey].join(":")} project={project.id} filters={filters} id={conversation} seed={conversation ? "" : seed} origin={origin} updateHistory={() => setHistoryRev(n => n + 1)}/>}
        {route === "history" && <section className="gtm-panel gtm-list">{history.data ? history.data.length ? history.data.map(h => <a key={h.id} href={"#/chat/" + encodeURIComponent(h.id)}>{h.label}<span>继续对话 ›</span></a>) : <p>暂无历史对话</p> : <Status error={history.error} retry={() => setHistoryRev(n => n + 1)}/>}</section>}
        {route === "help" && <section className="gtm-panel gtm-help"><h2>工作台使用指南</h2><dl>
          <div><dt>筛选数据</dt><dd>选择渠道、品类和周期，点击「查询」。页面中的破折号表示该项数据未知。</dd></div>
          <div><dt>查看分析依据</dt><dd>点击总结下的「查看依据」或数据行的「查看」，核对来源、观测时间和证据编号。</dd></div>
          <div><dt>对比竞品</dt><dd>在「竞品洞察分析」输入型号，切换产品对比、用户价值、卖点称重和价量联动。</dd></div>
          <div><dt>处理事项</dt><dd>在价格巡检、待办或订阅报告中打开明细，选择当前账号可执行的操作。</dd></div></dl><a href="#/daily">返回每日重点工作</a></section>}
      </main></div>{action && result.data && <ConfirmAction {...action} scope={viewScope} snapshot={result.data.snapshot_id} close={() => setAction(null)} done={msg => {setAction(null);setMessage(msg);refresh();}}/>}
  </div>;
}
