import { useEffect, useRef, useState } from "react";
import { Dialog, Sources } from "../DetailDialog";
import { gtm } from "../client";
import type { Action, Row, Scope } from "../contract";
import { projectDetail, type DetailProjection, type DetailRef } from "./projection";
import css from "./workbench.css?raw";

function Body({data}: {data: DetailProjection}) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const shadow = host.current!.shadowRoot || host.current!.attachShadow({mode:"open"});
    const style = document.createElement("style");
    style.textContent = css + "\n:host{display:block;color:#1d2129;--text:#1d2129;--muted:#697386;--primary:#0064fa;--line:#e7e9ee} .modal-body :empty{display:none} .modal-body{padding:0}";
    const el = document.createElement("div"); el.className = "modal-body";
    el.append(projectDetail(data, document)); shadow.replaceChildren(style,el);
  },[data]);
  return <div ref={host}/>;
}
export default function BoundDetail({row,scope,snapshot,close,act}: {
  row: Row; scope: Scope; snapshot: string; close: () => void; act: (a:Action,row:Row) => void
}) {
  const [path,setPath] = useState<DetailRef[]>([row.drilldown!]);
  const selected = path[path.length-1];
  const [state,setState] = useState<{data?: DetailProjection; error?:string}>({});
  const [revision,setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setState({});
    gtm.detail(scope,snapshot,selected,controller.signal).then(data=>{
      if (!controller.signal.aborted) setState({data});
    }).catch((e:Error)=>{if (!controller.signal.aborted) setState({error:e.message});});
    return () => controller.abort();
  },[scope.project_id,scope.category_code,snapshot,selected,revision]);
  const data = state.data;
  return <Dialog title={data?.title || selected.label} close={close}>
    {path.length>1 && <button onClick={()=>setPath(p=>p.slice(0,-1))}>返回上一级</button>}
    {data ? <><Body data={data}/><Sources items={data.evidence}/>
      <footer>{data.links.map(link=><button key={link.kind+link.record_id} onClick={()=>setPath(p=>[...p,link])}>{link.label}</button>)}
        {path.length===1 && row.actions.map(a=><button key={a.operation} className="primary" onClick={()=>act(a,row)}>{a.label}</button>)}</footer></> :
      <p role="status">{state.error || "正在读取详情…"} {state.error && <button onClick={()=>setRevision(n=>n+1)}>重试</button>}</p>}
  </Dialog>;
}
