// Link the auxiliary panels to the selected record. The 0916 source contains
// these panels but several of its entry buttons still point to retired screens.
(() => {
  const byId = id => document.getElementById(id);
  function button(parentSelector, label, open) {
    const item = document.createElement("button");
    item.className = "btn";
    item.type = "button";
    item.textContent = label;
    item.onclick = open;
    document.querySelector(parentSelector).prepend(item);
  }
  function textFields(fields) {
    for (const [id, value] of Object.entries(fields)) byId(id).textContent = value || "—";
  }
  button("#page-own-monitor .page-actions", "合规总览", () => goPage("dashboard"));
  pageTitles.dashboard = "价格合规总览";
  byId("page-dashboard").querySelector("[onclick*=\"goPage('alerts'\"]").onclick = () => goPage("own-monitor");
  button("#handlePriceModal .modal-foot", "整改通知单", () => {
    notifySelected = [];
    byId("notifyAlertCount").textContent = "1";
    byId("notifySearchInput").value = "";
    renderNotifyPicked();
    byId("notifySuggest").classList.remove("show");
    openModal("notifyModal");
  });
  button("#rivalEvidenceModal .rival-evidence-foot", "调价摘要", () => {
    const r = currentRivalEvidence;
    textFields({rivalPriceTitle:r.product + " · 调价详情", rivalPriceProduct:r.product,
      rivalPriceChannel:r.shop, rivalPriceCurrent:r.price, rivalPriceBase:r.original,
      rivalPriceChange:r.gap, rivalPriceMeta:r.meta, rivalPriceShot:r.shot});
    openModal("rivalPriceModal");
  });
  button("#launchEncyclopediaModal .launch-modal-footer", "产品档案", () => {
    const p = currentLaunchProduct;
    if (!p) return;
    textFields({wikiModalTitle:p.brand + " " + p.name + " · 竞品百科",wikiBrand:p.brand,
      wikiModel:p.name,wikiPosition:p.position,wikiUnits:p.sales,wikiRevenue:p.revenue,
      wikiPrice:p.price,wikiLaunchDate:p.date,wikiChannel:p.channel,wikiImpact:p.impact});
    byId("wikiSellingPoints").replaceChildren(...Array.from(byId("launchModalPoints")?.children ||
      document.querySelectorAll("#launchEncyclopediaModal .sell-point"), el => el.cloneNode(true)));
    const fields = document.createDocumentFragment();
    for (const [label,value] of [["品牌",p.brand],["产品型号",p.name],["品类",p.category],["市场定位",p.position]]) {
      const dt = document.createElement("dt"), dd = document.createElement("dd");
      dt.textContent = label; dd.textContent = value || "—"; fields.append(dt,dd);
    }
    byId("wikiProductInfo").replaceChildren(fields);
    openModal("competitorWikiModal");
  });
  const rows = byId("page-own-monitor").querySelectorAll("tbody tr");
  let model, channel;
  for (const row of rows) {
    model = row.querySelector(".model-cell")?.innerText.trim() || row.querySelector(".model-cell")?.textContent.trim() || model;
    channel = row.querySelector(".channel-cell")?.textContent.trim() || channel;
    const cells = Array.from(row.cells).filter(c => !c.matches(".model-cell,.channel-cell"));
    const data = {m:model,ch:channel,shop:cells[1].textContent.trim(),cur:cells[3].textContent.trim(),
      base:cells[4].textContent.trim(),gap:cells[5].textContent.trim(),lv:cells[6].textContent.trim()};
    const open = row.querySelector("[onclick^='openEvidence']");
    if (open) open.onclick = () => openEvidence(data.m,data.ch,data.gap,data.shop,data.cur,data.base,"样例巡检记录",data.lv);
  }
  const historyPage = byId("page-history");
  const search = historyPage.querySelector("input");
  search.addEventListener("input", () => {
    const needle = search.value.trim().toLowerCase();
    historyPage.querySelectorAll("[data-hid]").forEach(el => {el.style.display = el.textContent.toLowerCase().includes(needle) ? "" : "none";});
  });
  // Parent and child dialogs can both be visible. Index them by opening order,
  // so a nested picker stays above its caller irrespective of template order.
  const open = openModal;
  let top = 1200;
  openModal = function(id) { open(id); byId(id).style.zIndex = String(++top); };
  completeReportExport = function() {
    const formats={PDF:"pdf",PPT:"pptx",Word:"docx",Excel:"xlsx"};
    const format=formats[document.querySelector("input[name=exportFormat]:checked")?.value];
    const title=byId("exportFileName").value.trim().slice(0,120);
    if (!title) {showToast("请填写文件名"); return;}
    const page=byId("reportDetailModal").classList.contains("show") ? byId("reportPreviewSheet") : document.querySelector(".page.active");
    const lines=page.innerText.split(/\n+/).map(s=>s.trim().slice(0,4000)).filter(Boolean).slice(0,1000);
    parent.postMessage({type:"gtm:export",format,title,lines},"*");
    showToast("正在生成样例报告…");
  };
  window.addEventListener("message",e=>{
    if(e.source!==parent || e.data?.type!=="gtm:export-result") return;
    if(e.data.ok) closeModal("exportReportModal");
    showToast(e.data.message);
  });
  completeReportShare = function() {
    closeModal("shareReportModal");showToast("已预览样例分享配置，实际投递由后台执行");
  };
  createReportSubscription = function() {
    const modal=byId("subscriptionModal");
    const [type,cycle,category,channels]=Array.from(modal.querySelectorAll("select"),el=>el.value);
    const [schedule,owner,name]=Array.from(modal.querySelectorAll("input:not([type=checkbox])"),el=>el.value.trim());
    if(!schedule || !owner) {showToast("请填写生成时间和负责人");return;}
    smartReports.unshift({id:Math.max(...smartReports.map(r=>r.id))+1,title:name || category+type+cycle,type,cycle,category,channels,
      status:"待人工确认",updated:"刚刚",owner,period:"待生成",next:schedule,version:"V1.0",week:true,
      summary:"样例订阅任务已创建，等待首份报告。",sku:"—",change:"—",actions:"—"});
    closeModal("subscriptionModal");resetSmartReportFilters();showToast("已创建本次样例会话的订阅任务");
  };
  queueReportAutoSave = function() {
    const report=smartReports.find(r=>r.id===currentSmartReportId);
    if(!report) return;
    report.title=byId("detailReportTitle").textContent.trim() || report.title;
    report.summary=byId("detailReportSummary").textContent.trim();
    byId("reportSaveState").textContent="本次会话已暂存";
  };
  viewBasePrice = function(btn) {
    const row=btn.closest("tr"), table=row.closest("table");
    const csvLine=xs=>xs.map(x=>'"'+x.textContent.trim().replaceAll('"','""')+'"').join(",");
    const csv="\ufeff"+[csvLine(Array.from(table.tHead.rows[0].cells).slice(0,-1)),csvLine(Array.from(row.cells).slice(0,-1))].join("\r\n");
    const url=URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8"}));
    const a=document.createElement("a");a.href=url;a.download=(row.dataset.ver || "底价版本")+".csv";a.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  copyReportLink = function() {parent.postMessage({type:"gtm:share-link",id:currentSmartReportId},"*");};
  window.addEventListener("message",e=>{
    if (e.source!==parent || e.data?.type!=="gtm:share-result") return;
    let field=byId("sampleShareLink");
    if (!field) {
      field=document.createElement("input");field.id="sampleShareLink";field.className="input";
      field.readOnly=true;field.setAttribute("aria-label","报告样例链接");
      byId("shareReportModal").querySelector(".modal-body").append(field);
    }
    field.value=e.data.link;field.focus();field.select();
    showToast(e.data.copied ? "已复制样例链接" : "可复制下方的样例链接");
  });
  sendNotice = function() {
    if (!notifySelected.length) {showToast("请至少选择一个群组或人员");return;}
    closeModal("notifyModal");showToast("已生成样例整改通知草稿 · "+notifySelected.join("、"));
  };
})();
