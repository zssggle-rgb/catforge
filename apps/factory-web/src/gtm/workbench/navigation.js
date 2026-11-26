// Embedded sample controls keep their own state. Only navigation crosses the frame boundary.
(() => {
  let current = "";
  let initialized = false;
  let historyId = "";
  const menu = document.querySelector(".small-nav-trigger");
  function setMenu(open) {
    document.body.classList.toggle("small-nav-open",open);
    menu.setAttribute("aria-expanded",String(open));
  }
  menu.addEventListener("click",()=>setMenu(!document.body.classList.contains("small-nav-open")));
  document.querySelector(".small-nav-backdrop").addEventListener("click",()=>setMenu(false));
  document.querySelector(".sidebar").addEventListener("click",e=>{
    if(e.target.closest(".nav-item,.history-item,.new-chat,.history-title")) setMenu(false);
  }, {capture:true}); // Some page handlers stop the click from bubbling.
  function selectedRoute() {
    const page = document.querySelector(".page.active")?.id.slice(5) || "daily";
    if (page === "competitor") {
      if (document.getElementById("panel-premium").classList.contains("active")) {
        return "premium/" + (document.querySelector(".premium-sub-panel.active")?.id.slice(6) || "value-index");
      }
      return "competitor/" + (document.querySelector("#analysisTabs .tab.active")?.dataset.target || "product");
    }
    if (page === "chat" && historyId && document.querySelector("#page-chat.chatting")) return "chat/" + historyId;
    if (page === "reports" && document.getElementById("reportDetailModal").classList.contains("show")) return "reports/"+currentSmartReportId;
    if (page === "help" && document.querySelector(".help-nav-item.active")) return "help/"+document.querySelector(".help-nav-item.active").getAttribute("href").slice(1);
    return page;
  }
  function publish() {
    if (!initialized) return;
    const next = selectedRoute();
    if (current !== next) {
      current = next;
      parent.postMessage({type:"gtm:route",route:next}, "*");
    }
  }
  const loadHistory = loadHistoryById;
  loadHistoryById = function(id) {historyId = id; loadHistory(id); publish();};
  const startChat = newChat;
  newChat = function() {historyId = ""; startChat(); publish();};
  // srcdoc inherits the host's document URL; native hash links would replace the frame.
  document.querySelectorAll(".help-nav-item").forEach(link => {
    link.addEventListener("click", event => event.preventDefault());
  });
  window.addEventListener("message", event => {
    if (event.source !== parent || event.data?.type !== "gtm:restore") return;
    const [page, detail] = String(event.data.route).split("/");
    if (!Object.hasOwn(pageTitles, page) && page !== "dashboard") return;
    if (initialized && selectedRoute() === event.data.route) return;
    initialized = false;
    document.querySelectorAll(".modal-mask.show").forEach(m => m.classList.remove("show"));
    if (page === "competitor" || page === "premium") {
      if (page === "competitor") openCompetitor(); else openPremium();
      const group = page === "competitor" ? "#analysisTabs" : "[data-group=premium-sub]";
      const tab = Array.from(document.querySelectorAll(group + " .tab")).find(t => t.dataset.target === detail);
      if (tab) tab.click();
    } else if (page === "chat") {
      if (detail && Object.hasOwn(historyConversations, detail)) loadHistoryById(detail);
      else newChat();
    } else {
      goPage(page);
      if (page==="reports" && detail && smartReports.some(r=>String(r.id)===detail)) openSmartReport(Number(detail));
      if (page==="help" && detail && Array.from(document.querySelectorAll(".help-nav-item")).some(a=>a.getAttribute("href")==="#"+detail)) scrollHelp(detail);
    }
    initialized = true;
    publish();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      const top = Array.from(document.querySelectorAll(".modal-mask.show")).sort((a,b) => Number(b.style.zIndex) - Number(a.style.zIndex))[0];
      if (top) closeModal(top.id);
    }
  });
  const watched = document.querySelectorAll(".page,.tab-panel,.premium-sub-panel,#analysisTabs .tab,.help-nav-item,#reportDetailModal");
  const observer = new MutationObserver(publish);
  watched.forEach(el => observer.observe(el, {attributes:true,attributeFilter:["class"]}));
  parent.postMessage({type:"gtm:ready"}, "*");
})();
