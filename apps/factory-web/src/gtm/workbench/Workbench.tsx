import { useEffect, useRef, useState } from "react";
import Button from "@douyinfe/semi-ui/lib/es/button";
import chartsUrl from "echarts/dist/echarts.min.js?url";
import { gtm } from "../client";
import { productDescription, productName, productTitle } from "../brand";
import { pages } from "../contract";
import layout from "./frame.html?raw";
import css from "./workbench.css?raw";
import theme from "./catforge.css?raw";
import inventory from "./value-inventory.js?raw";
import controller from "./interactions.js?raw";
import navigation from "./navigation.js?raw";
import details from "./detail-links.js?raw";
import pagination from "./pagination.js?raw";
import { screenMarkup } from "./screens";

const body = layout.replace(/<!--screen:([\w-]+)-->/g, (_, id: string) => screenMarkup(id))
  .replaceAll("{{productName}}", productName)
  .replaceAll("{{productDescription}}", productDescription);
const extraPages = {help: "帮助中心", chat: "新建对话", history: "历史记录", dashboard: "经营看板"};
const titles: Record<string,string> = {...pages, ...extraPages};
function route(value: unknown) {
  if (typeof value !== "string" || !/^[\w-]+(?:\/[\w-]+)?$/.test(value)) return "daily";
  return Object.hasOwn(titles, value.split("/")[0]) ? value : "daily";
}
const locationRoute = () => route(window.location.hash.replace(/^#\/?/, ""));
function buildDocument(records: Record<string, unknown>) {
  const origin = window.location.origin;
  const script = new URL(chartsUrl, origin).href;
  const json = JSON.stringify(records).replace(/</g, "\\u003c");
  // srcdoc has its own cascade. Pass the same Semi theme tokens used by the React shell.
  const shell = getComputedStyle(document.body);
  const tokens = ["primary","primary-light-default","text-0","text-1","text-2","bg-0","border","fill-0","danger"]
    .map(name => "--semi-color-" + name)
    .filter(name => shell.getPropertyValue(name).trim())
    .map(name => name + ":" + shell.getPropertyValue(name)).join(";");
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' ${origin}; img-src data: blob:; style-src 'unsafe-inline'; font-src data:; form-action 'none'; base-uri 'none'">
    <style>:root{${tokens}}${css}\n${theme}</style><script src="${script}"></script></head><body>${body}
    <script>window.gtmRecords=${json}</script><script>${controller}</script><script>${inventory}</script><script>${details}</script><script>${pagination}</script><script>${navigation}</script></body></html>`;
}

export default function Workbench({project}: {project: string}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const exporting = useRef(false);
  const [documentHtml, setDocumentHtml] = useState("");
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const load = new AbortController();
    setError("");
    gtm.sampleScenario(project, load.signal).then(records => {
      if (!load.signal.aborted) setDocumentHtml(buildDocument(records));
    }).catch((e: Error) => {if (!load.signal.aborted) setError(e.message);});
    return () => load.abort();
  }, [project, revision]);
  useEffect(() => {
    const restore = () => frame.current?.contentWindow?.postMessage({type: "gtm:restore", route: locationRoute()}, "*");
    function receive(event: MessageEvent) {
      if (!frame.current || event.source !== frame.current.contentWindow || event.origin !== "null") return;
      if (event.data?.type === "gtm:ready") restore();
      if (event.data?.type === "gtm:share-link" && Number.isSafeInteger(event.data.id)) {
        const url=new URL(window.location.href); url.hash="/reports/"+event.data.id;
        const link=url.href;
        const sender=frame.current.contentWindow;
        navigator.clipboard?.writeText(link).then(()=>sender?.postMessage({type:"gtm:share-result",link,copied:true},"*"))
          .catch(()=>sender?.postMessage({type:"gtm:share-result",link,copied:false},"*"));
        if (!navigator.clipboard) sender?.postMessage({type:"gtm:share-result",link,copied:false},"*");
      }
      if (event.data?.type === "gtm:export" && !exporting.current) {
        const {format,title,lines} = event.data;
        if (!["pdf","pptx","docx","xlsx"].includes(format) || typeof title!=="string" || !title.trim() || title.length>120 ||
            !Array.isArray(lines) || lines.length>1000 || !lines.every(v=>typeof v==="string" && v.length<=4000)) return;
        exporting.current = true;
        const result = (message:string, ok:boolean) => frame.current?.contentWindow?.postMessage({type:"gtm:export-result",message,ok},"*");
        gtm.exportSample(project,format,title,lines).then(blob=>{
          const href=URL.createObjectURL(blob), a=document.createElement("a");
          a.href=href; a.download=title.replace(/[\\/:*?"<>|]/g,"-")+"."+format; a.click();
          setTimeout(()=>URL.revokeObjectURL(href),1000);result("样例报告已生成",true);
        }).catch((e:Error)=>result(e.message,false)).finally(()=>{exporting.current=false;});
      }
      if (event.data?.type === "gtm:route") {
        const next = route(event.data.route);
        document.title = titles[next.split("/")[0]] + " · " + productName;
        if (next !== locationRoute()) window.history.pushState(null, "", "#/" + next);
      }
    }
    window.addEventListener("message", receive);
    window.addEventListener("hashchange", restore);
    return () => {window.removeEventListener("message", receive); window.removeEventListener("hashchange", restore);};
  }, [project]);
  if (!documentHtml) return <main className="gtm gtm-boot" role="status"><h1>{productName}</h1>
    {error || "正在读取工作台样例…"} {error && <Button onClick={() => setRevision(n => n + 1)}>重试</Button>}</main>;
  return <iframe ref={frame} title={productTitle} sandbox="allow-scripts allow-downloads"
    style={{position:"fixed",inset:0,width:"100%",height:"100%",border:0,background:"#f5f6f8"}} srcDoc={documentHtml}/>;
}
