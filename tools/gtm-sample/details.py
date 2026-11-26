"""Entity-scoped sample projections for the same workbench detail templates."""
import fixtures as f


PAGES = {"own-evidence": "own-monitor", "rival-evidence": "rival-monitor",
         "rival-price-history": "rival-monitor", "rival-price-summary": "rival-monitor",
         "launch-encyclopedia": "launch", "product-profile": "launch", "task": "todo-center", "report": "reports"}


def read(kind, record_id, category, snapshot, state):
    page = PAGES.get(kind)
    if not page:
        return None
    scope = {"category_code": category, "period": "7d", "limit": 100}
    view = f.business_view(page, scope, state)
    if snapshot != view["snapshot_id"]:
        raise ValueError("快照已变化，请刷新父页")
    record = next((r for table in view["tables"] if table["id"] == page for r in table["rows"] if r["id"] == record_id), None)
    if not record:
        return None
    def display_fields(row):
        return {item["label"]:item["value"] for item in row["detail"]}
    cells = display_fields(record)
    def money(key):
        v = cells.get(key)
        return None if v is None else f"¥{v:,}"
    values = {"title":record["title"], "model": cells.get("型号"), "brand":cells.get("品牌"), "channel":cells.get("渠道")}
    lists, tables, links = {}, {}, []
    if page in ("own-monitor", "rival-monitor"):
        values.update({"paid_price":money("到手价（元）"), "floor_price":money("月度底价（元）"),
                       "prior_price":money("上次到手价（元）"), "gap":money("价差（元）" if page=="own-monitor" else "调价（元）"),
                       "level":cells.get("预警等级"), "source":record["evidence"][0]["source"],
                       "snapshot_note":record["evidence"][0]["excerpt"]})
        if kind == "rival-evidence":
            links = [("rival-price-history","价格明细"),("rival-price-summary","调价摘要")]
        if kind == "rival-price-history":
            rows = [item for t in view["tables"] if t["id"]==page for r in t["rows"]
                    if (item:=display_fields(r)).get("型号") == cells["型号"] and item.get("渠道") == cells["渠道"]]
            cols = ["观测日期","渠道","到手价（元）","上次到手价（元）","调价（元）"]
            tables["history"] = {"columns":cols, "rows":[[item.get(k) for k in cols] for item in rows]}
    elif page == "launch":
        values.update({"name":cells["型号"], "brand_initial":cells["品牌"][:1], "subtitle":cells["核心规格"],
                       "price":money("首发价（元）"),"launch_date":cells["上市日期"],"category":"电视"})
        lists["claims"] = cells["核心规格"].split(" · ")
        tables["specs"] = {"columns":["字段","值"],"rows":[[k,v] for k,v in cells.items()]}
        if kind=="launch-encyclopedia":
            links = [("product-profile","产品档案")]
    elif page == "reports":
        values.update({"summary":cells.get("正文"),"metadata":" · ".join(cells[k] for k in ["周期","状态","更新时间"])})
    else:
        values.update({"type":cells.get("类型"),"status":cells.get("状态"),"deadline":cells.get("截止时间"),"owner":cells.get("负责人")})
    return {"version":"0916","project_id":f.PROJECT,"category_code":category,"snapshot_id":snapshot,
            "kind":kind,"record_id":record_id,"title":record["title"],"values":values,"tables":tables,"lists":lists,
            "evidence":record["evidence"],"links":[{"kind":k,"record_id":record_id,"label":label} for k,label in links]}
