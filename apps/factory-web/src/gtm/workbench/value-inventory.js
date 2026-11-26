// The sample BFF provides the observations. Classification names belong to the view.
(() => {
  const names = {all:"全部", high:"高价值", base:"门槛", pending:"待激活", missing:"缺失"};
  const records = window.gtmRecords.valueInventory || [];
  const filters = document.querySelector(".inventory-filters");
  const body = document.getElementById("valueInventoryRows");

  function render(group) {
    const rows = group === "all" ? records : records.filter(item => item.group === group);
    body.replaceChildren();
    for (const item of rows) {
      const row = body.insertRow();
      const title = row.insertCell();
      const claim = document.createElement("strong");
      claim.textContent = item.claim;
      title.append(claim);
      if (item.source) {
        const source = document.createElement("small");
        source.textContent = "对标竞品　" + item.source;
        title.append(source);
      }
      row.insertCell().textContent = names[item.group] || "待分类";
      const detail = row.insertCell();
      detail.textContent = item.benefits?.length ? item.benefits.join("、") : item.action || "—";
    }
    if (!rows.length) {
      const empty = body.insertRow().insertCell();
      empty.colSpan = 3;
      empty.textContent = "当前分类暂无卖点";
    }
    for (const button of filters.children) {
      button.setAttribute("aria-pressed", String(button.dataset.group === group));
    }
  }
  for (const [group, label] of Object.entries(names)) {
    const button = document.createElement("button");
    const count = document.createElement("span");
    button.type = "button";
    button.dataset.group = group;
    count.textContent = group === "all" ? records.length : records.filter(item => item.group === group).length;
    button.append(label, count);
    button.addEventListener("click", () => render(group));
    filters.append(button);
  }
  render("all");
})();
