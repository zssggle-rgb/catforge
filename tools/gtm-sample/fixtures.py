"""Deterministic HTTP examples for the GTM frontend. No database or CatForge credentials."""
from datetime import date, timedelta

DAY = "2026-09-10"
AS_OF = DAY + "T09:30:00+08:00"
PROJECT = "gtm-sample"
CATEGORIES = {"TV": "电视", "AC": "空调"}
CHANNELS = {"jd": "京东", "tmall": "天猫", "pdd": "拼多多", "dy": "抖音"}
PAGES = {"daily", "key-model", "own-monitor", "rival-monitor", "launch", "competitor", "premium", "todo-center", "reports"}
TABS = {"competitor": {"product", "value", "weight", "price-volume"}, "premium": {"value-index", "voc"}}
FACETS = {"brand": "品牌", "severity": "预警等级", "status": "状态", "owner": "负责人", "cadence": "周期"}
FACET_COLUMNS = {"brand": "品牌", "severity": "预警等级", "status": "状态", "owner": "负责人", "cadence": "周期"}
PAGE_FACETS = {"key-model": ["brand"], "own-monitor": ["severity", "status"], "launch": ["brand"],
               "todo-center": ["status", "owner"], "reports": ["status", "cadence"]}
FIELD_KEYS = {
    "型号": "model", "品牌": "brand", "渠道": "channel", "店铺名称": "shop_name", "到手价（元）": "net_price_cny",
    "观测日期": "observed_date", "上次到手价（元）": "previous_price_cny", "调价（元）": "price_change_cny",
    "月度底价（元）": "floor_price_cny", "价差（元）": "floor_gap_cny", "预警等级": "severity", "处理状态": "status",
    "核心规格": "specification", "上市日期": "launch_date", "首发价（元）": "launch_price_cny", "文件": "filename",
    "状态": "status", "活动": "campaign", "开始日期": "start_date", "结束日期": "end_date", "任务标题": "title",
    "类型": "type", "截止时间": "due_at", "负责人": "owner", "报告名称": "report_name", "品类": "category",
    "周期": "cadence", "订阅": "subscription_status", "更新时间": "updated_at", "正文": "body", "期间": "period",
    "销量（台）": "sales_volume_units", "销额（元）": "sales_amount_cny", "成交均价（元）": "weighted_avg_price_cny",
    "定位": "role", "显示技术": "display_type", "刷新率": "refresh_rate", "用户任务": "user_task", "卖点": "claim",
    "反馈": "feedback", "证据": "evidence_summary", "估计价值（元）": "estimated_value_cny", "观察窗口": "window",
    "可比成交": "comparable_sales", "预测销量": "forecast_units", "范围": "scope", "可比口径": "population",
    "综合指数": "composite_index", "主题": "topic", "证据范围": "evidence_population", "指数": "index",
}
MODELS = ["65E7Q", "75E8N Pro", "55E5N", "65WS8Q"]
SALES = [(MODELS[0], 392, 1867837.63), (MODELS[1], 168, 1175832), (MODELS[2], 240, 599760)]
CATALOG = {"own-model": {"hs65": "海信 65E7Q", "hs75": "海信 75E8N Pro", "hs55": "海信 55E5N"},
           "competitor": {"tcl65": "TCL 65Q9L PRO", "mi65": "小米 S Pro 65", "sky75": "创维 75A7H PRO"},
           "brand": {"hisense": "海信", "tcl": "TCL", "mi": "小米", "sky": "创维"}}


def options(mapping):
    return [{"id": key, "label": value} for key, value in mapping.items()]


def context():
    categories = [{**c, "subcategories": [{"id": "flat" if c["id"] == "TV" else "home",
                                           "label": "平板电视" if c["id"] == "TV" else "家用空调"}]} for c in options(CATEGORIES)]
    return {"version": "1", "mode": "sample", "user": {"name": "样例用户", "role": "GTM产品经理"},
            "projects": [{"id": PROJECT, "label": "品铸", "categories": categories, "channels": options(CHANNELS)}]}


def initial_state():
    chats = {}
    for key, title in [("compare-65", "65E7Q竞品对标分析"), ("value-65", "高价值卖点量价验证"), ("premium", "海信品牌溢价趋势")]:
        chats[key] = {"id": key, "category": "TV", "label": title, "messages": [
            {"role": "user", "text": title, "evidence": []}, {"role": "assistant", "text": "可查看同品类的参数、来源卖点与观测价格，再核对适用条件。",
             "evidence": [evidence(key, "样例分析记录", title)]}]}
    return {"revision": 1, "closed": set(), "ack": set(), "ignored": {}, "uploads": {}, "floor_imports": {}, "campaigns": {}, "subscriptions": set(), "models": list(MODELS[:3]),
            "reports": {"weekly": "彩电竞品价格周报", "launch": "竞品新品洞察"}, "published": {"weekly", "launch"}, "content": {}, "chats": chats, "receipts": {}}


def evidence(key, source, excerpt, day=DAY):
    return {"evidence_id": "sample-" + key, "source": source, "observed_at": day,
            "excerpt": excerpt, "source_file_id": "gtm-sample-v1", "raw_row_id": key}


def field(key, label, kind="text", value=""):
    return {"key": key, "label": label, "kind": kind, "required": True, "value": value}


def action(key, label, fields=()):
    return {"operation": key, "label": label, "fields": list(fields)}


def row(key, title, values, ev, actions=()):
    return {"id": key, "title": title, "cells": values, "evidence": [ev],
            "detail": [{"label": k, "value": v} for k, v in values.items()], "actions": list(actions)}


def metric(label, value, unit="", hint="", **extra):
    return {"label": label, "value": value, "unit": unit, "hint": hint, **extra}


def insight(label, title, tone, body, bullets, ev, question=None):
    return {"label": label, "title": title, "tone": tone, "body": body, "bullets": bullets, "evidence": [ev], "question": question}


def table(key, title, rows, headers, scope, target=None):
    q = scope.get("query", "").strip().casefold()
    filtered = [r for r in rows if not q or q in " ".join([r["title"], *(str(v) for v in r["cells"].values())]).casefold()]
    facets = []
    for facet in PAGE_FACETS.get(key, []):
        column = "处理状态" if key == "own-monitor" and facet == "status" else FACET_COLUMNS[facet]
        values = sorted({r["cells"].get(column) for r in rows if r["cells"].get(column)})
        facets.append({"key": facet, "label": FACETS[facet], "options": options({x: x for x in values})})
        if scope.get(facet):
            filtered = [r for r in filtered if r["cells"].get(column) == scope[facet]]
    start, size = int(scope.get("offset", 0)), int(scope.get("limit", 20))
    if target:
        start, size = 0, 3
    result = {"id": key, "title": title, "columns": [{"key": FIELD_KEYS[c], "label": c} for c in headers],
              "rows": [{**r, "cells": {FIELD_KEYS[c]: value for c, value in r["cells"].items()}} for r in filtered[start:start + size]],
              "total": len(filtered), "_facets": facets}
    if target:
        result["target"] = target
    return result


def window(scope):
    anchor = date.fromisoformat(DAY)
    period = scope.get("period", "today")
    if period == "custom":
        return date.fromisoformat(scope["date_from"]), date.fromisoformat(scope["date_to"])
    end = anchor - timedelta(days=int(period == "yesterday"))
    return end - timedelta(days={"today": 0, "yesterday": 0, "7d": 6, "30d": 29}[period]), end


def empty_view(page, scope):
    return {"version": "1", "project_id": PROJECT, "category_code": scope["category_code"], "page": page,
            "tab": scope.get("tab", ""), "snapshot_id": "sample-20260910-v1", "as_of": AS_OF,
            "status": "ready", "notice": None, "insights": [], "metrics": [], "charts": [], "tables": [], "actions": []}


def price_rows(scope, state, competitor=False):
    first, last = window(scope)
    rows = []
    models = ["65Q9L PRO", "S Pro 65", "75A7H PRO"] if competitor else MODELS
    for age in range(7):
        day = date.fromisoformat(DAY) - timedelta(days=age)
        if not first <= day <= last:
            continue
        for i, ch in enumerate(("pdd", "jd", "tmall", "dy", "pdd", "jd")[:[6, 4, 3, 6, 2, 4, 5][age]]):
            if scope.get("channel") and scope["channel"] != ch:
                continue
            model = models[(i + age) % len(models)]
            if competitor:
                own = list(CATALOG["own-model"])[i % 3]
                rival = list(CATALOG["competitor"])[(i + age) % 3]
                if scope.get("model_id") and scope["model_id"] != own:
                    continue
                if scope.get("competitor_ids") and rival not in scope["competitor_ids"]:
                    continue
            key = ("rival" if competitor else "price") + f"-{age}-{i}"
            price = [4899, 5522, 4299, 6799, 2299, 5999][i] + age * 30
            ev = evidence(key, "样例店铺价格快照", f"{day} {CHANNELS[ch]}，{model} 到手价 ¥{price:,}。", str(day))
            values = {"型号": model, "渠道": CHANNELS[ch], "店铺名称": CHANNELS[ch] + "旗舰店", "到手价（元）": price, "观测日期": str(day)}
            if competitor:
                values.update({"上次到手价（元）": price + 200, "调价（元）": -200})
                actions = []
            else:
                diff = [-300, -100, 0, 200, -200, 100][(i + age) % 6]
                values.update({"月度底价（元）": price - diff, "价差（元）": diff, "预警等级": "严重" if diff <= -300 else "一般" if diff < 0 else "正常",
                               "处理状态": "已忽略" if key in state["ignored"] else "已处理" if key in state["ack"] else "待处理" if diff < 0 else "—"})
                actions = [action("acknowledge-alert", "确认处理"), action("ignore-alert", "忽略预警", [field("reason", "忽略原因")])] if values["处理状态"] == "待处理" else []
            rows.append(row(key, model + " · " + CHANNELS[ch], values, ev, actions))
    return rows


def launches(scope):
    start, end = window(scope)
    result = []
    for i, (brand, model, specs, price, ch, age) in enumerate([
        ("TCL", "65Q9L PRO", "Mini LED · 120 Hz", 5522, "jd", 0), ("小米", "S Pro 65", "65 英寸 · 4K", 4199, "pdd", 0),
        ("创维", "75A7H PRO", "75 英寸 · 低反射屏", 6299, "tmall", 1)]):
        day = date.fromisoformat(DAY) - timedelta(days=age)
        if start <= day <= end and (not scope.get("channel") or scope["channel"] == ch):
            result.append(row("launch-" + str(i), brand + " " + model, {"品牌": brand, "型号": model, "核心规格": specs,
                              "上市日期": str(day), "首发价（元）": price, "渠道": CHANNELS[ch]},
                              evidence("launch-" + str(i), "样例新品档案", model + " · " + specs, str(day))))
    return result


def prices(page, scope, state, view):
    own, rivals, new = price_rows(scope, state), price_rows(scope, state, True), launches(scope)
    alerts = [r for r in own if r["cells"]["价差（元）"] < 0]
    counts = {ch: sum(r["cells"]["渠道"] == ch for r in alerts) for ch in CHANNELS.values()}
    sources = evidence("inspection", "样例巡检批次", f"当前范围 {len(own)} 条观测，{len(alerts)} 项异常。")
    if page in ("daily", "own-monitor"):
        view["metrics"] = [metric("巡检SKU数", len({r["cells"]["型号"] for r in own}), hint="当前窗口去重型号", target="own-monitor"),
                           metric("价格异常数", len(alerts), hint="低于有效底价的观测", tone="red", target="own-monitor"),
                           metric("违规率", round(100 * len(alerts) / len(own), 2) if own else None, "%", "异常观测 / 有效观测"),
                           metric("涉及渠道数", len({r["cells"]["渠道"] for r in own}), hint="有有效价格的渠道")]
        view["insights"].append(insight("重点关注", "价格异常", "red", sources["excerpt"],
            [f"{c} · {n} 项价格异常" for c, n in counts.items() if n], sources, "查看价格异常处理依据"))
    if page in ("daily", "rival-monitor") and rivals:
        view["insights"].append(insight("市场动态", "竞品调价", "orange", "发现可比店铺的到手价变动，需核对优惠资格和观测时间。",
            [r["title"] + " · 调低 200 元" for r in rivals[:2]], rivals[0]["evidence"][0], "分析竞品调价影响"))
    if page in ("daily", "launch") and new:
        view["insights"].append(insight("新品监测", "竞品上新", "purple", f"当前范围有 {len(new)} 款新品上市。",
            [r["title"] + " · " + r["cells"]["核心规格"] for r in new], new[0]["evidence"][0], "对比新品核心卖点"))
    if page == "daily":
        end = window(scope)[1]
        trend = price_rows({**scope, "period": "custom", "date_from": str(end - timedelta(days=6)), "date_to": str(end)}, state)
        dates = sorted({r["cells"]["观测日期"] for r in trend})
        view["charts"] = [{"title": "近7天价格违规趋势", "kind": "line", "unit": "项", "points": [
            {"label": d[5:], "value": sum(r["cells"]["观测日期"] == d and r["cells"]["价差（元）"] < 0 for r in trend)} for d in dates]},
            {"title": "异常渠道分布", "kind": "distribution", "unit": "项", "points": [{"label": c, "value": n} for c, n in counts.items()]}]
        sales = empty_view("key-model", scope)
        sales_view(scope, state, sales)
        view["tables"].append({**sales["tables"][0], "title": "重点产品销额·销量·均价", "target": "key-model"})
    for key, label, rows, cols in [
        ("own-monitor", "我品价格巡检明细", alerts if page == "daily" else own, ["型号", "渠道", "店铺名称", "到手价（元）", "月度底价（元）", "预警等级", "处理状态"]),
        ("rival-monitor", "竞品调价明细", rivals, ["型号", "渠道", "上次到手价（元）", "到手价（元）", "调价（元）", "观测日期"]),
        ("launch", "竞品上新明细", new, ["品牌", "型号", "核心规格", "上市日期", "首发价（元）", "渠道"])]:
        if page in ("daily", key):
            view["tables"].append(table(key, label, rows, cols, scope, key if page == "daily" else None))
    if not own and not new:
        view.update(status="unavailable", notice="所选范围无价格或新品观测。", metrics=[], charts=[], insights=[])


def business_view(page, scope, state):
    v = empty_view(page, scope)
    v["snapshot_id"] = f"sample-20260910-v{state['revision']}"
    if scope["category_code"] != "TV":
        return {**v, "status": "unavailable", "notice": "空调样例尚无已发布的业务快照。"}
    if page in ("daily", "own-monitor", "rival-monitor", "launch"):
        prices(page, scope, state, v)
        if page == "own-monitor":
            v["actions"] = [action("import-floor", "底价维护", [field("attachment_id", "底价文件", "file")]),
                            action("create-campaign", "新建活动", [field("name", "活动名称"), field("start", "开始日期", "date"), field("end", "结束日期", "date")])]
            for key, label, rows, cols in [("floors", "底价导入记录", state["floor_imports"], ["文件", "状态"]),
                                           ("campaigns", "价格活动", state["campaigns"], ["活动", "开始日期", "结束日期", "状态"])]:
                if rows:
                    v["tables"].append(table(key, label, list(rows.values()), cols, {**scope, "offset": 0}))
    elif page == "key-model":
        sales_view(scope, state, v)
    elif page in ("competitor", "premium"):
        analysis(page, scope, v)
    elif page == "todo-center":
        items = []
        for r in price_rows(scope, state):
            if r["cells"]["价差（元）"] >= 0:
                continue
            key = "task-" + r["id"]
            done = key in state["closed"]
            items.append(row(key, r["title"] + "价格整改", {"任务标题": r["title"] + "价格整改", "类型": "价格整改", "状态": "已完成" if done else "待处理",
                "截止时间": r["cells"]["观测日期"] + " 18:00", "负责人": "样例用户"}, r["evidence"][0], [] if done else [action("complete-task", "标为已完成")]))
        v["tables"] = [table(page, "待办任务", items, ["任务标题", "类型", "状态", "截止时间", "负责人"], scope)]
        v["metrics"] = [metric("待处理", sum(r["cells"]["状态"] == "待处理" for r in items)), metric("已完成", sum(r["cells"]["状态"] == "已完成" for r in items))]
    elif page == "reports":
        items = []
        start, end = window(scope)
        for key, name in state["reports"].items():
            if not start <= date.fromisoformat(DAY) <= end or scope.get("channel"):
                continue
            subscribed = key in state["subscriptions"]
            published = key in state["published"]
            actions = ([action("unsubscribe-report", "取消订阅") if subscribed else action("subscribe-report", "订阅报告")] if published else
                       [action("edit-report", "编辑报告", [field("body", "报告正文", "textarea", state["content"].get(key, ""))]),
                        action("publish-report", "确认发布")])
            items.append(row(key, name, {"报告名称": name, "品类": "电视", "周期": "周报", "状态": "已发布" if published else "待人工确认",
                "订阅": "已订阅" if subscribed else "未订阅", "更新时间": DAY, "正文": state["content"].get(key, name + " · 价格观测与经营摘要。")}, evidence(key, "样例报告档案", name), actions))
        v["actions"] = [action("create-report", "新建报告任务")]
        v["tables"] = [table("reports", "报告档案", items, ["报告名称", "品类", "周期", "状态", "订阅", "更新时间"], scope)]
    for idx, section in enumerate(v["tables"]):
        facets = section.pop("_facets", [])
        if idx == 0 and page != "daily":
            v["facets"] = facets
    if page in ("competitor", "premium") and v["tables"] and v["tables"][0]["total"]:
        v["actions"] = [action("create-report", "生成分析报告")]
    return v


def sales_view(scope, state, v):
    v["actions"] = [action("set-key-models", "管理重点产品")]
    start, end = window(scope)
    first, last = date(2026, 6, 8), date(2026, 6, 14)
    available = start <= first and end >= last
    items = []
    for model, units, amount in SALES:
        if model not in state["models"]:
            continue
        selected = available and not scope.get("channel")
        values = {"品牌": "海信", "型号": model, "期间": "26W24" if selected else "—", "销量（台）": units if selected else None,
                  "销额（元）": amount if selected else None, "成交均价（元）": round(amount / units, 2) if selected else None}
        items.append(row(model, "海信 " + model, values, evidence(model, "样例重点型号清单", "26W24 按专业电商、平台电商统计；日成交缺源。", "2026-06-14")))
    if not available or scope.get("channel"):
        v.update(status="partial", notice="缺少当前口径的成交数据。选择全渠道、自定义 2026-06-08 至 2026-06-14 可查看周样例。")
    v["tables"] = [table("key-model", "重点产品明细", items, ["品牌", "型号", "期间", "销量（台）", "销额（元）", "成交均价（元）"], scope)]
    if available and not scope.get("channel"):
        v["metrics"] = [metric("65E7Q 周销量", 392, "台", "专业电商、平台电商", basis={
            "grain": "周", "population": "专业电商＋平台电商", "source_batch": "sample-26W24", "coverage_from": str(first), "coverage_to": str(last), "synced_at": AS_OF})] if "65E7Q" in state["models"] else []
    elif available and scope.get("channel") in ("jd", "tmall") and "65E7Q" in state["models"]:
        channel = scope["channel"]
        units = {"jd": 110, "tmall": 115}[channel]
        v.update(status="partial", notice="平台周汇总采用独立统计总体，部分金额不可用。")
        v["tables"] = [table("platform-sales", "平台周表现", [row("hs65-" + channel, "65E7Q",
            {"品牌": "海信", "型号": "65E7Q", "期间": "26W24", "渠道": CHANNELS[channel], "销量（台）": units, "销额（元）": None},
            evidence("26W24-" + channel, "平台周汇总样例", f"该平台周销量 {units} 台。", "2026-06-14"))],
            ["品牌", "型号", "渠道", "期间", "销量（台）", "销额（元）"], scope)]


def analysis(page, scope, v):
    panel = scope.get("tab")
    schemas = {
        "product": ("产品对比", ["型号", "定位", "显示技术", "刷新率"], [
            ["海信 65E7Q", "我品", "Mini LED", "170 Hz"], ["TCL 65Q9L PRO", "竞品", "QD-Mini LED", "288 Hz"]]),
        "value": ("用户价值分析", ["型号", "用户任务", "卖点", "反馈"], [["海信 65E7Q", "多设备游戏", "四路 HDMI 2.1", "减少切换设备时换线"]]),
        "weight": ("卖点价值评估", ["型号", "卖点", "证据", "估计价值（元）"], [["海信 65E7Q", "高刷新率", "高刷体验相关评论", None]]),
        "price-volume": ("实际量价关系", ["型号", "观察窗口", "可比成交", "预测销量"], [["海信 65E7Q", "同期同渠道", "待核对", None]]),
        "value-index": ("价格指数明细", ["品牌", "范围", "可比口径", "综合指数"], [["海信", "65英寸", "同尺寸、配置与同期渠道", None], ["TCL", "65英寸", "同尺寸、配置与同期渠道", None]]),
        "voc": ("品牌VOC横向对比", ["品牌", "主题", "证据范围", "指数"], [["海信", "品牌信任", "品牌对象明确的评论", None], ["TCL", "售后体验", "品牌服务评论", None]])}
    title, keys, rows = schemas[panel]
    if page == "competitor":
        own = scope.get("model_id", "")
        if own and own != "hs65":
            return v.update(status="unavailable", notice="所选我品当前没有已发布的分析样例。")
        if panel == "product":
            rows.extend([["小米 S Pro 65", "竞品", "Mini LED", None], ["创维 75A7H PRO", "竞品", "Mini LED", None]])
            selected = {CATALOG["competitor"][k] for k in scope.get("competitor_ids", [])}
            rows = [r for r in rows if not selected or r[1] == "我品" or r[0] in selected]
        elif scope.get("competitor_ids") and scope["competitor_ids"] != ["tcl65"]:
            return v.update(status="unavailable", notice="所选竞品组合暂无同口径分析结果。")
    elif scope.get("brand_ids"):
        selected = {CATALOG["brand"][k] for k in scope["brand_ids"]}
        rows = [r for r in rows if r[0] in selected]
    if scope.get("channel") or not window(scope)[0] <= date.fromisoformat(DAY) <= window(scope)[1]:
        return v.update(status="unavailable", notice="当前范围无同口径分析快照。")
    ev = evidence(panel, "样例分析快照", "卖点来自商详，价值解释与金额估计分别记录。")
    items = [row(panel + str(i), values[0], dict(zip(keys, values)), ev) for i, values in enumerate(rows)]
    v.update(method_version="sample-v1", review_status="样例", confidence=None)
    if panel in ("weight", "price-volume", "voc", "value-index"):
        v.update(status="partial", notice="当前样例缺少经验证的模型或行业分母，对应估计值保留为空。")
    v["tables"] = [table(panel, title, items, keys, scope)]
    v["insights"] = [insight("分析范围", title, "teal", ev["excerpt"], ["同一快照内按型号与来源回查证据。"], ev)] if v["tables"][0]["total"] else []
