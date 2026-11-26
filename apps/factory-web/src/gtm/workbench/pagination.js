// Keep merged model/channel cells aligned when a page starts halfway through
// a group. The original HTML contains only the first group of launch records.
(() => {
  function addLaunchRecords(tbody) {
    const seen = new Set(Array.from(tbody.rows, row => row.cells[1].textContent.trim()));
    for (const [category,items] of Object.entries(homeLaunchCatalog)) {
      for (const p of items) {
        if (tbody.rows.length >= 12 || seen.has(p.m)) continue;
        seen.add(p.m);
        const row = tbody.insertRow();
        for (const value of [p.b,p.m,p.sell.join(" · "),p.d,p.p,p.impact]) row.insertCell().textContent = value;
        const btn = document.createElement("button");
        btn.type = "button"; btn.className = "btn sm"; btn.textContent = "竞品百科";
        btn.onclick = () => openLaunchEncyclopedia(p.b,p.m,p.pos,p.u,p.r,p.p,p.d,p.s,category,p.pos,p.sell,p.impact);
        row.insertCell().append(btn);
      }
    }
  }
  function expandSpans(rows) {
    const held = [];
    for (const row of rows) {
      const original = Array.from(row.cells);
      let pos = 0;
      for (const cell of original) {
        while (held[pos]?.remaining) {
          const copy = held[pos].cell.cloneNode(true); copy.rowSpan = 1;
          row.insertBefore(copy,cell); held[pos].remaining--; pos++;
        }
        if (cell.rowSpan>1) {held[pos]={cell,remaining:cell.rowSpan-1};cell.rowSpan=1;}
        pos += cell.colSpan;
      }
    }
  }
  function setup(id) {
    const page = document.getElementById("page-"+id);
    const pager = page.querySelector(".el-pagination");
    const table = page.querySelector(id==="rival-monitor" ? "#rivalMonitorTableWrap table" : "table");
    if (!table?.tBodies[0] || !pager) return;
    const rows = Array.from(table.tBodies[0].rows);
    if (id==="launch") addLaunchRecords(table.tBodies[0]);
    const all = Array.from(table.tBodies[0].rows);
    expandSpans(all);
    const size = pager.querySelector("select");
    size.onchange = null;
    size.prepend(new Option("5条/页","5"));
    if (id==="launch") size.value="5";
    let index=0, filtered=all;
    function render() {
      const count = Math.max(1,Math.ceil(filtered.length/parseInt(size.value,10)));
      index=Math.min(index,count-1);
      const visible = new Set(filtered.slice(index*parseInt(size.value,10),(index+1)*parseInt(size.value,10)));
      all.forEach(row => {row.style.display=visible.has(row)?"":"none";});
      pager.querySelector(".ep-total").textContent="共 "+filtered.length+" 条";
      pager.querySelectorAll("button").forEach(b=>b.remove());
      function add(label,target,disabled,active) {
        const b=document.createElement("button");b.type="button"; b.className="ep-btn"+(active?" active":"")+(disabled?" disabled":"");
        b.textContent=label;b.disabled=disabled;b.onclick=()=>{index=target;render();};pager.append(b);
      }
      add("‹",index-1,index===0,false);
      for(let n=0;n<count;n++) add(String(n+1),n,false,n===index);
      add("›",index+1,index===count-1,false);
    }
    function filter() {
      const headers=Array.from(table.tHead?.rows[0].cells || [],c=>c.textContent.replace("↕","").trim());
      const requirements=[];
      for (const group of page.querySelectorAll(".filters .filter")) {
        const el=group.querySelector("select"), label=group.querySelector("label")?.textContent.trim();
        const column=headers.indexOf(label);
        if (!el || column<0) continue;
        const value=el.selectedOptions[0]?.text.trim();
        if (value && !["全部","全渠道","全部品牌","全部状态","全部类型"].includes(value)) requirements.push([column,value]);
      }
      filtered=all.filter(row=>requirements.every(([col,value])=>row.cells[col]?.textContent.includes(value)));
      index=0;render();
    }
    size.onchange=()=>{index=0;render();};
    page.querySelectorAll(".filters button").forEach(b=>{if(b.textContent.trim()==="查询") b.onclick=filter;});
    if (id==="own-monitor") document.getElementById("ownHandleStatusSelect").onchange=filter;
    if (rows.length) render();
  }
  for (const id of ["own-monitor","rival-monitor","launch","todo-center","key-model"]) setup(id);
})();
