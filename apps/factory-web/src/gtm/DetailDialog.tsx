import type { ReactNode } from "react";
import Modal from "@douyinfe/semi-ui/lib/es/modal";
import type { Evidence } from "./contract";

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
