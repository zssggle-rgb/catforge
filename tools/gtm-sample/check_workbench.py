"""Compare the signed-off screens with a deployed frontend, using an installed browser."""
import argparse
import hashlib
import json
from html import escape
from pathlib import Path
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright


def inspect(frame, save):
    states = {}
    visited_modals = set()
    def snap(label, selector):
        view = frame.locator(selector).first
        view.wait_for(state="visible")
        info = view.evaluate("""e => ({
          titles: [...e.querySelectorAll('h1,h2,h3,h4,.card-title,.modal-head,.ds-title')].filter(n=>n.offsetWidth).map(n=>n.innerText.trim().replace(/\\s+/g,' ')),
          columns: [...e.querySelectorAll('th')].filter(n=>n.offsetWidth).map(n=>n.innerText.trim()),
          rows: e.querySelectorAll('tbody tr').length,
          forms: [...e.querySelectorAll('input,textarea,select')].map(n=>n.id || n.name || n.type),
          text: e.innerText.trim().length,
          content: e.innerText.trim().replace(/\\s+/g,' ')
        })""")
        assert info["text"] > 1, label
        states[label] = info
        if save:
            gradient_surfaces = view.locator(
                ":is(.model-builder,.monitor-ai-summary,.ai-card,.premium-index-card,.price-record,"
                ".inventory-head,.report-ai-head,.rival-model-title,.chat-analysis-title,.chat-value-item):visible"
            ).evaluate_all("nodes => nodes.filter(n=>getComputedStyle(n).backgroundImage.includes('gradient')).map(n=>n.className)")
            assert not gradient_surfaces, (label, gradient_surfaces)
            if not selector.startswith("#page-") and not selector.endswith("Modal"):
                view.evaluate("el=>el.scrollIntoView({block:'start',behavior:'instant'})")
            frame.page.screenshot(path=save / (label + ".png"), animations="disabled")
    def click(selector):
        frame.locator(selector + ":visible").first.click(timeout=3500)
    def action(name, container=".page.active"):
        click(container + " [onclick^=\"" + name + "(\"]")
    def nav(page):
        if page == "help": click(".topbar [onclick*=help]")
        elif page == "history": click(".history-title [onclick]")
        elif page == "chat": click(".new-chat")
        elif page == "dashboard": frame.evaluate("goPage('dashboard')")
        else: click(".nav-item[data-page='" + page + "']")
        region = "#page-" + ("competitor" if page == "premium" else page)
        frame.locator(region).wait_for(state="visible")
        return region
    def modal(label, mid, opener=None):
        if opener: click(opener)
        snap(label, "#" + mid)
        visited_modals.add(mid)
    def close(mid):
        click("#" + mid + " :is(.modal-close,.kpm-close,[onclick^='closeModal('])")

    for page in ("daily","key-model","own-monitor","launch","rival-monitor","competitor","premium","todo-center","reports","chat","history","help","dashboard"):
        snap("入口-" + page, nav(page))
    nav("daily")
    action("openDailyTop3Modal"); modal("每日-TOP3选择","keyProductModal"); close("keyProductModal")
    for i in range(frame.locator(".daily-model-card:visible").count()):
        frame.locator(".daily-model-card:visible").nth(i).click()
        snap("每日-型号趋势-" + str(i+1), "#page-daily")
    action("openEvidence"); modal("每日-我品证据","evidenceModal"); close("evidenceModal")
    action("openHandleModal"); modal("每日-处理任务","handlePriceModal"); close("handlePriceModal")
    action("openRivalEvidence"); modal("每日-竞品调价证据","rivalEvidenceModal"); close("rivalEvidenceModal")
    action("toggleRivalAlertShowAll"); snap("每日-全部竞品调价","#page-daily")
    action("openLaunchEncyclopedia"); modal("每日-新品百科","launchEncyclopediaModal"); close("launchEncyclopediaModal")
    action("openExportModal"); modal("每日-导出报告","exportReportModal"); close("exportReportModal")
    nav("key-model"); action("openKeyProductModal"); modal("重点产品-管理型号","keyModelModal"); close("keyModelModal")
    action("sortKeyModelTable"); snap("重点产品-排序","#page-key-model")
    nav("own-monitor")
    for mid, label in (("basePriceModal","底价版本"),("activityModal","活动期间")):
        modal("巡检-"+label,mid,"#page-own-monitor [onclick*='" + mid + "']"); close(mid)
    action("openEvidence"); modal("巡检-单条价格证据","evidenceModal"); close("evidenceModal")
    action("openHandleModal"); modal("巡检-异常处理","handlePriceModal"); close("handlePriceModal")
    nav("rival-monitor")
    for toggle, cancel, label in (("toggleSingleSelectDropdown","cancelSingleSelect","我品型号单选"),("toggleMultiSelectDropdown","cancelMultiSelect","竞品多选")):
        action(toggle); snap("竞品监控-"+label,"#page-rival-monitor"); action(cancel)
    action("openRivalEvidence"); modal("竞品监控-调价证据","rivalEvidenceModal"); close("rivalEvidenceModal")
    action("openRivalPriceDetailMonitor"); modal("竞品监控-价格明细","rivalPriceDetailModal"); close("rivalPriceDetailModal")
    nav("launch")
    for i in range(frame.locator("#page-launch [onclick^='openLaunchEncyclopedia']:visible").count()):
        frame.locator("#page-launch [onclick^='openLaunchEncyclopedia']:visible").nth(i).click()
        modal("上新-产品百科-"+str(i+1),"launchEncyclopediaModal"); close("launchEncyclopediaModal")
    nav("competitor")
    for mid,label in (("ownParamsModal","我品参数上传"),("competitorModal","自定义竞品")):
        modal("竞品洞察-"+label,mid,"#page-competitor [onclick*='" + mid + "']"); close(mid)
    for target in ("product","value","weight","pricevolume"):
        click("#analysisTabs [data-target='"+target+"']"); snap("竞品洞察-"+target,"#panel-"+target)
        if target == "product":
            for i in range(3):
                frame.locator("[onclick^='switchCompetitorMetric']:visible").nth(i).click()
                snap("产品对比-周趋势-"+str(i+1),"#competitiveTrendSection")
            action("toggleSellingPoints"); snap("产品对比-全部卖点","#sellingPointSection")
        if target == "weight":
            sel=frame.locator("#weightPointSelect")
            for i in range(1,sel.locator("option").count()):
                sel.select_option(index=i); snap("卖点称重-卖点-"+str(i+1),"#panel-weight")
    nav("premium")
    action("togglePremiumBrandMenu"); snap("品牌溢价-对比品牌","#brandScope"); action("togglePremiumBrandMenu")
    for target in ("value-index","voc-index"):
        click("[data-group=premium-sub] [data-target='"+target+"']"); snap("品牌溢价-"+target,"#panel-"+target)
    nav("todo-center"); action("showTodoDetail"); modal("待办-任务详情","todoDetailModal"); close("todoDetailModal")
    nav("reports")
    modal("报告-新建订阅","subscriptionModal","#page-reports [onclick*=subscriptionModal]"); close("subscriptionModal")
    click("#reportGridViewBtn" if frame.locator("#reportGridViewBtn").count() else "[onclick*=\"setSmartReportView('grid'\"]")
    snap("报告-卡片视图","#smartReportContainer")
    click("#reportListViewBtn"); click("#reportPageControls [onclick*=\"goSmartReportPage(2\"]")
    snap("报告-第二页","#smartReportContainer"); click("#reportPageControls [onclick*=\"goSmartReportPage(1\"]")
    action("openSmartReport"); modal("报告-阅读与版本","reportDetailModal")
    click("#detailEditBtn"); snap("报告-编辑器与助手","#reportDetailModal")
    action("askReportAssistant","#reportAiAssistant"); frame.locator(".report-ai-msg.user").first.wait_for()
    snap("报告-助手修改","#reportAiAssistant")
    for mid,label in (("exportReportModal","导出配置"),("shareReportModal","分享配置")):
        modal("报告-"+label,mid,"#reportDetailModal [onclick*='"+mid+"']"); close(mid)
    close("reportDetailModal")
    nav("chat"); action("toggleAttachMenu"); snap("对话-附件菜单","#attachMenu"); action("toggleAttachMenu")
    ids=frame.locator(".sidebar [data-hid]").evaluate_all("nodes=>nodes.map(n=>n.dataset.hid)")
    for hid in ids:
        click(".sidebar [data-hid='"+hid+"']"); snap("对话-"+hid,"#chatScroll")
    nav("daily"); nav("help")
    links=frame.locator(".help-nav-item").evaluate_all("nodes=>nodes.map(n=>n.getAttribute('href'))")
    for link in links:
        click(".help-nav-item[href='"+link+"']"); snap("帮助-"+link[1:],link)
    # The reference has three orphaned dialogs; the port must open them through the UI.
    for mid, label, source, trigger, parent in (
        ("notifyModal","整改通知单","own-monitor","openHandleModal","handlePriceModal"),
        ("competitorWikiModal","产品档案","launch","openLaunchEncyclopedia","launchEncyclopediaModal"),
        ("rivalPriceModal","调价摘要","rival-monitor","openRivalEvidence","rivalEvidenceModal")
    ):
        if save:
            nav(source); action(trigger)
            frame.locator("#"+parent).get_by_role("button",name=label,exact=True).click()
        else:
            frame.evaluate("id=>openModal(id)",mid)
        modal("保留面板-"+label,mid); close(mid)
        if save: close(parent)
    assert visited_modals==set(frame.locator(".modal-mask").evaluate_all("nodes=>nodes.map(n=>n.id)"))
    return states


def check_inventory(frame, reference):
    original = reference.locator(".value-tier-card").evaluate_all("""cards => cards.flatMap(card =>
      [...card.querySelectorAll('.tier-item')].map(item => ({
        claim: item.querySelector('b').textContent,
        copy: [...item.querySelectorAll('.benefit-tags span, p')].map(el => el.textContent),
        source: item.querySelector('.competitor-source')?.textContent.replace(/^来源：/, '') || '',
        group: [...card.classList].at(-1)
      })))""")
    assert len(original) == 10
    frame.locator(".nav-item[data-page=competitor]").click()
    frame.locator("#analysisTabs [data-target=value]").click()
    table = frame.locator("#valueInventoryRows")
    for group in ("high", "base", "pending", "missing", "all"):
        button = frame.locator(f".inventory-filters button[data-group={group}]")
        button.focus()
        button.press("Enter")
        expected = [item for item in original if group == "all" or item["group"] == group]
        assert button.get_attribute("aria-pressed") == "true" and table.locator("tr").count() == len(expected)
        for row, item in zip(table.locator("tr").all(), expected):
            assert row.locator("strong").inner_text() == item["claim"]
            assert all(part in row.inner_text() for part in [*item["copy"], item["source"]])
    frame.locator(".inventory-guide summary").click()
    assert frame.locator(".inventory-guide dd:visible").count() == 4
    frame.locator(".inventory-guide summary").click()


def check_actions(page, url):
    page.goto(url+"#/premium/voc-index")
    page.wait_for_selector("iframe")
    frame=page.frames[-1]
    frame.locator("#panel-voc-index").wait_for()
    assert frame.locator("#premiumVocCompare .premium-voc-card").count()>=2
    frame.locator(".nav-item[data-page=rival-monitor]").click()
    row = frame.locator("#page-rival-monitor tbody tr:visible").first
    row.locator("[onclick^=openRivalEvidence]").click()
    dialog = frame.locator("#rivalEvidenceModal")
    prices = frame.evaluate("() => currentRivalEvidence")
    assert dialog.locator("#rivalEvidenceProduct").inner_text() == prices["product"]
    assert dialog.locator("#rivalEvidencePrice").inner_text() == prices["price"]
    assert dialog.locator("#rivalEvidenceGap").inner_text() == prices["gap"]
    lines = dialog.locator("#rivalEvidenceShot dl > div")
    plain = lambda s: "".join(s.split())
    assert [plain(s) for s in lines.all_text_contents()] == [plain(s) for s in prices["shot"].split("·")]
    assert dialog.locator(".fake-shot,.chain-tag,.res-shot").count() == 0
    dialog.locator(".modal-close").click()
    frame.locator(".nav-item[data-page=own-monitor]").click()
    frame.locator("#page-own-monitor").get_by_role("button",name="2",exact=True).click()
    visible=frame.locator("#page-own-monitor tbody tr:visible")
    assert visible.count()==5
    visible.first.locator("[onclick^=openEvidence]").click()
    expected=visible.first.locator(".model-cell").text_content()
    assert frame.locator("#evidenceProduct").inner_text()==expected.strip()
    frame.locator("#evidenceModal .modal-close").click()
    frame.locator("#page-own-monitor").get_by_role("button",name="合规总览").click()
    frame.locator("#page-dashboard .attention").first.click()
    frame.locator("#page-own-monitor").wait_for()
    frame.locator(".nav-item[data-page=launch]").click()
    frame.locator("#page-launch").get_by_role("button",name="2",exact=True).click()
    second=frame.locator("#page-launch tbody tr:visible").first
    expected=second.locator("td").nth(1).inner_text()
    second.get_by_role("button",name="竞品百科").click()
    assert frame.locator("#launchModalModel").inner_text()==expected
    frame.locator("#launchEncyclopediaModal .modal-close").click()
    frame.locator(".nav-item[data-page=reports]").click()
    frame.locator("#smartReportContainer [onclick^=openSmartReport]").first.click()
    frame.locator("#detailEditBtn").click()
    frame.locator("#detailReportSummary").fill("样例验收：人工修改报告正文")
    frame.locator("#detailViewBtn").click()
    assert "人工修改报告正文" in frame.locator("#detailReportSummary").inner_text()
    frame.locator("#reportDetailModal [onclick*=exportReportModal]").click()
    for fmt,ext in (("PDF","pdf"),("PPT","pptx"),("Word","docx"),("Excel","xlsx")):
        if not frame.locator("#exportReportModal").is_visible():
            frame.locator("#reportDetailModal [onclick*=exportReportModal]").click()
        frame.locator('input[name=exportFormat][value="'+fmt+'"]').check()
        with page.expect_download(timeout=15000) as file:
            frame.locator("#exportReportModal .primary").click()
        assert file.value.suggested_filename.endswith("."+ext)
        with Path(file.value.path()).open("rb") as f:
            assert f.read(2)==(b"%P" if ext=="pdf" else b"PK")
        frame.locator("#exportReportModal").wait_for(state="hidden")
    page.reload();page.wait_for_selector("iframe");frame=page.frames[-1]
    frame.locator("#reportDetailModal").wait_for()
    frame.locator("#reportDetailModal .modal-close").click()
    before=frame.locator("#reportStatAll").inner_text()
    frame.locator("#page-reports [onclick*=subscriptionModal]").click()
    frame.locator("#subscriptionModal .primary").click()
    assert int(frame.locator("#reportStatAll").inner_text())==int(before)+1
    return ["品牌VOC深链接","竞品调价证据的型号、价格、幅度和优惠明细与所选记录一致","巡检第二页与同行证据","合规总览往返","上新第二页与匹配百科",
            "报告编辑与阅读","PDF、PPTX、DOCX、XLSX真实下载","报告详情刷新恢复","新建订阅后报告数更新"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference",type=Path)
    parser.add_argument("--url",default="http://127.0.0.1:18166/gtm/")
    parser.add_argument("--out",type=Path,required=True)
    opts=parser.parse_args()
    opts.out.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel="chrome")
        def tab():
            page=browser.new_page(viewport={"width":1440,"height":960},locale="zh-CN")
            page.set_default_timeout(4000)
            return page
        deployed=tab()
        errors=[]
        deployed.on("pageerror",lambda e:errors.append(e.stack or str(e)))
        deployed.goto(opts.url)
        deployed.wait_for_selector("iframe")
        frame=deployed.frames[-1]
        frame.locator(".nav-item").first.wait_for()
        chart_src=frame.locator("script[src]").first.get_attribute("src")
        charts=deployed.request.get(urljoin(opts.url,chart_src)).body()
        original=tab()
        original.route("**/echarts.min.js",lambda r:r.fulfill(content_type="text/javascript",body=charts))
        original.goto(opts.reference.resolve().as_uri())
        expected=inspect(original.main_frame,None)
        actual=inspect(frame,opts.out)
        differences={key:{field:[actual[key][field],val] for field,val in record.items()
                         if field not in ("text","content") and actual[key][field]!=val} for key,record in expected.items()}
        unchanged_content=("竞品洞察-weight","品牌溢价-value-index",
                           "品牌溢价-voc-index","重点产品-管理型号","巡检-底价版本","巡检-活动期间","报告-新建订阅","报告-导出配置","报告-分享配置")
        for key in unchanged_content:
            assert actual[key]["content"]==expected[key]["content"], key+" 子页面正文不一致"
        renamed_copy = {
            "竞品洞察-product": [("AI总结与建议","产品对比结论"),("AI推荐竞品","推荐竞品")],
            "竞品洞察-pricevolume": [("AI总结与建议","量价变化"),("AI AI解读","成交表现"),("模型预测 AI 推荐方案","模型预测 推荐方案")],
        }
        for key, labels in renamed_copy.items():
            updated = expected[key]["content"]
            for old, new in labels:
                updated = updated.replace(old, new)
            assert actual[key]["content"] == updated, key+" 业务内容被改变"
        check_inventory(frame, original.main_frame)
        assert actual["竞品洞察-value"]["titles"] == ["卖点分类明细"]
        assert actual["竞品洞察-value"]["columns"] == ["卖点","分类","用户利益点 / 行动建议"]
        assert actual["竞品洞察-value"]["rows"] == 10
        for field in ("titles","columns","rows"):
            differences["竞品洞察-value"].pop(field,None)
        for key in ("入口-competitor","入口-premium"):
            assert actual[key]["rows"] == expected[key]["rows"] + 10
            differences[key].pop("rows",None)
        # New section headings replace generic AI labels; all other headings keep their order.
        headings = {"AI总结与建议":{"产品对比结论","竞品调价概况","量价变化","上新概况"},
            "AI结论与策略":{"品牌溢价结论"}, "AI智能归因分析":{"重点型号表现分析"},
            "我品价格巡检智能总结":{"价格巡检概况"}}
        for key, changes in differences.items():
            if "titles" in changes:
                current, prior = changes["titles"]
                if len(current)==len(prior) and all(a==b or a in headings.get(b,set()) for a,b in zip(current,prior)):
                    changes.pop("titles")
        for key, title in (("每日-我品证据","价格巡检证据"),("巡检-单条价格证据","价格巡检证据"),
                           ("每日-竞品调价证据","竞品调价证据"),("竞品监控-调价证据","竞品调价证据"),
                           ("保留面板-调价摘要","调价摘要")):
            assert actual[key]["titles"] == [title+" ×"]
            differences[key].pop("titles",None)
        assert actual["入口-launch"]["rows"]==12 and expected["入口-launch"]["rows"]==5
        differences["入口-launch"].pop("rows",None)
        # These headers in the source are static placeholders rather than selected-record names.
        for key in ("保留面板-产品档案",):
            differences[key].pop("titles",None)
        differences={key:val for key,val in differences.items() if val}
        ids=lambda f:f.locator(".page,.modal-mask,.tab-panel,.premium-sub-panel").evaluate_all("nodes=>nodes.map(n=>n.id).sort()")
        screen_ids=ids(frame)
        assert screen_ids==ids(original.main_frame)
        actions=check_actions(deployed,opts.url)
        actions.append("逐条核对终稿的10项卖点、18条用户利益、行动建议与来源，键盘切换全部分类")
        live=tab()
        def live_context(route):
            response=route.fetch()
            context=response.json();context["mode"]="live"
            route.fulfill(json=context)
        live.route("**/gtm/v1/context",live_context)
        requests=[]
        live.on("request",lambda req:requests.append(req.url))
        live.on("pageerror",lambda e:errors.append(e.stack or str(e)))
        live.goto(opts.url+"#/rival-monitor")
        live.locator(".gtm-snapshot").wait_for()
        live.get_by_role("button",name="查看",exact=True).first.click()
        live.locator("#rivalEvidencePrice").wait_for()
        assert "¥" in live.locator("#rivalEvidencePrice").inner_text()
        live.get_by_role("button",name="价格明细",exact=True).click()
        live.locator("#rivalPriceDetailTableWrap tbody tr").first.wait_for()
        assert any("/details/rival-price-history" in x for x in requests)
        assert not any("sample-scenarios" in x for x in requests)
        actions.append("真实模式契约模拟：竞品监控→选中记录证据→同一记录的历史价格")
        live.goto(opts.url+"#/competitor")
        live.get_by_role("button",name="用户价值分析",exact=True).click()
        value_table = live.locator(".gtm-matrix")
        value_table.get_by_text("四路 HDMI 2.1",exact=True).wait_for()
        assert value_table.locator("th").all_text_contents() == ["型号","用户任务","卖点","反馈","操作"]
        value_table.get_by_role("button",name="查看明细").first.click()
        live.get_by_role("dialog").wait_for()
        actions.append("真实模式契约模拟：用户价值表格读取接口字段并打开行明细")
        phone=browser.new_page(viewport={"width":390,"height":844},locale="zh-CN")
        phone.goto(opts.url);phone.wait_for_selector("iframe")
        handheld=phone.frames[-1];handheld.get_by_role("button",name="打开导航").click()
        handheld.locator(".nav-item[data-page=reports]").click()
        handheld.locator("#page-reports").wait_for()
        assert handheld.evaluate("document.documentElement.scrollWidth<=window.innerWidth")
        actions.append("390px 宽度打开导航并进入订阅报告")
        phone.goto(opts.url+"#/competitor/value")
        handheld=phone.frames[-1]
        inventory=handheld.locator(".value-inventory")
        inventory.wait_for()
        inventory.evaluate("n=>n.scrollIntoView({block:'start'})")
        assert inventory.evaluate("n=>n.scrollWidth<=window.innerWidth && n.getBoundingClientRect().top>=document.querySelector('.topbar').getBoundingClientRect().bottom-1")
        handheld.locator(".inventory-filters button[data-group=missing]").click()
        assert handheld.locator("#valueInventoryRows tr").count()==2
        actions.append("390px 宽度查看卖点表格并筛选缺失项")
        report={"reference_sha256":hashlib.sha256(opts.reference.read_bytes()).hexdigest(),
                "url":opts.url,"screen_ids":screen_ids,"states":list(actual),"matching_body_text":list(unchanged_content),
                "actions":actions,"differences":differences,"errors":errors}
        (opts.out/"验收结果.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({k:v for k,v in report.items() if k in ("errors","differences")},ensure_ascii=False),len(actual),flush=True)
        assert not differences and not errors
        cards="".join('<figure><a href="'+escape(k)+'.png"><img loading="lazy" src="'+escape(k)+'.png" alt="'+escape(k)+'"></a><figcaption>'+escape(k)+'</figcaption></figure>' for k in actual)
        (opts.out/"index.html").write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GTM 0916 逐页验收</title><style>body{margin:32px;background:#f5f6f8;color:#172337;font:15px system-ui}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:18px}figure{margin:0;background:white;border:1px solid #dfe5ed;border-radius:8px;overflow:hidden}img{width:100%;display:block}figcaption{padding:10px 14px}</style><h1>GTM 0916 逐页验收</h1><p>奥维 A 样例环境 · '+str(len(actual))+' 个页面状态 · 点击图片查看原尺寸</p><main>'+cards+'</main></html>',encoding="utf-8")
        browser.close()


if __name__ == "__main__":
    main()
