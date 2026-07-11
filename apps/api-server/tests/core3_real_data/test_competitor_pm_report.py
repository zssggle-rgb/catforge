import json

from app.services.core3_real_data.analyst import competitor_answer
from app.services.core3_real_data.analyst.competitor_answer import ReportPublishResult
from app.services.core3_real_data.analyst.competitor_pm_report import (
    build_pm_comparison_payload,
    pm_business_output_issue,
    render_pm_comparison_report,
)


def test_pm_comparison_report_renders_four_products_and_business_sections() -> None:
    products = [
        _product("海信 65E7Q", 5949, 251, "高端画质升级", "影院沉浸观影", "画质配置解释加价"),
        _product("创维 65A7H PRO", 5637, 217, "高端画质升级", "高端画质体验", "家装融合更适合客厅"),
        _product("TCL 65Q9L PRO", 5522, 194, "高端画质升级", "高端画质体验", "高亮画质配置升级"),
        _product("创维 65A6F ULTRA", 4415, 322, "高端画质升级", "影院沉浸观影", "同价位核心配置完整"),
    ]
    payload = build_pm_comparison_payload(
        title="海信 65E7Q 与重点竞品的用户选择对比报告",
        product_views=products,
        substitution_rows=[
            {
                "name": "创维 65A7H PRO",
                "与本品重合的选择理由": "高端画质升级",
                "竞品更突出的理由": "家装融合",
                "本品保留的理由": "高亮画质",
                "替代程度": "中等（6/10）",
            },
            {
                "name": "TCL 65Q9L PRO",
                "与本品重合的选择理由": "高端画质升级",
                "竞品更突出的理由": "智能控制",
                "本品保留的理由": "杜比和护眼",
                "替代程度": "中等（5/10）",
            },
            {
                "name": "创维 65A6F ULTRA",
                "与本品重合的选择理由": "影院和游戏体验",
                "竞品更突出的理由": "同价位配置完整",
                "本品保留的理由": "芯片和高亮画质",
                "替代程度": "较强（8/10）",
            },
        ],
        evidence_report_url="https://my.feishu.cn/docx/EvidenceReport",
    )

    markdown = render_pm_comparison_report(title=payload["title"], payload=payload)

    assert payload["schema_version"] == "competitor_pm_comparison_v1"
    assert "| 比较内容 | 海信 65E7Q | 创维 65A7H PRO | TCL 65Q9L PRO | 创维 65A6F ULTRA |" in markdown
    assert "## 一、四款产品分别卖多少钱、卖得怎么样" in markdown
    assert "## 二、四款产品真正强在哪里" in markdown
    assert "## 六、产品重点讲什么，用户实际理解了什么" in markdown
    assert "## 七、用户为什么会选择四款产品" in markdown
    assert "## 八、用户在四款产品之间会怎样取舍" in markdown
    assert "## 九、四款产品的用户价值是否传达完整" in markdown
    assert "[查看竞品识别、评分和证据依据](https://my.feishu.cn/docx/EvidenceReport)" in markdown
    assert "创维 65A6F ULTRA价格最低" in markdown
    assert "创维 65A6F ULTRA周均销量最高" in markdown
    for forbidden in ("BF_", "TASK_", "TG_", "M12D", "WTP", "建议验证", "应该降价", "销量追赶"):
        assert forbidden not in markdown


def test_pm_comparison_report_omits_purchase_sections_without_published_profiles() -> None:
    products = [_product("本品", 5000, 100, "高端画质", "影院观影", None), _product("竞品", 4800, 90, "高端画质", "影院观影", None)]

    payload = build_pm_comparison_payload(
        title="本品与重点竞品的用户选择对比报告",
        product_views=products,
        substitution_rows=[],
        evidence_report_url=None,
    )
    markdown = render_pm_comparison_report(title=payload["title"], payload=payload)

    assert "## 七、用户为什么会选择" not in markdown
    assert "## 八、用户在" not in markdown
    assert "## 九、" not in markdown
    assert "本品与重点竞品总览" in markdown


def test_pm_business_output_guard_rejects_internal_codes() -> None:
    assert pm_business_output_issue("用户主要比较高端画质。") is None
    assert pm_business_output_issue("内部维度 BF_PREMIUM_PICTURE_UPGRADE") == "用户选择对比报告包含未解析的内部字段。"
    assert pm_business_output_issue("gate_reasons=missing") == "用户选择对比报告包含未解析的内部字段。"


def test_competitor_answer_publishes_independent_reports_and_adds_card_links(monkeypatch) -> None:
    calls: list[str] = []

    def fake_publish_report(*, title: str, markdown: str, with_report: str) -> ReportPublishResult:
        calls.append(title)
        assert markdown.startswith(f"# {title}")
        assert with_report == "feishu-doc"
        token = "PmReport" if "用户选择对比" in title else "EvidenceReport"
        return ReportPublishResult(status="created", url=f"https://my.feishu.cn/docx/{token}")

    monkeypatch.setattr(competitor_answer, "_publish_report", fake_publish_report)
    answer = competitor_answer.build_competitor_answer(
        target={
            "sku_code": "TV_TARGET",
            "brand_name": "海信",
            "model_name": "65E7Q",
            "screen_size_inch": 65,
            "size_tier": "large_60_69",
            "price_band_in_size_tier": "mid_high",
            "price_wavg": 5949,
            "avg_weekly_sales_volume": 251,
        },
        target_fact_brief={"sections": {}},
        competitors=[_competitor()],
        top_n=1,
        with_report="feishu-doc",
    )

    assert calls == [
        "海信 65E7Q 重点竞品识别与分析依据报告",
        "海信 65E7Q 与重点竞品的用户选择对比报告",
    ]
    assert answer["report_url"] == "https://my.feishu.cn/docx/EvidenceReport"
    assert answer["evidence_report_url"] == "https://my.feishu.cn/docx/EvidenceReport"
    assert answer["pm_comparison_report_url"] == "https://my.feishu.cn/docx/PmReport"
    dashboard = answer["dashboard_payload"]
    assert dashboard["pm_comparison_report_link"] == {
        "label": "查看用户选择对比",
        "url": "https://my.feishu.cn/docx/PmReport",
        "type": "pm_comparison_report",
    }
    card_text = json.dumps(answer["feishu_card_payload"], ensure_ascii=False)
    assert "查看用户选择对比" in card_text
    assert "查看分析依据" in card_text
    assert "https://my.feishu.cn/docx/PmReport" in card_text
    assert "https://my.feishu.cn/docx/EvidenceReport" in card_text


def test_oversized_card_keeps_pm_and_evidence_buttons() -> None:
    card = {
        "schema": "2.0",
        "config": {"summary": {"content": "重点竞品看板"}},
        "header": {},
        "body": {
            "elements": [
                {"tag": "markdown", "content": "很长的内容" * 10_000},
                {"tag": "button", "element_id": "view_pm_comparison_report"},
                {"tag": "button", "element_id": "view_report"},
            ]
        },
    }

    compact = competitor_answer._trim_feishu_card(card)

    button_ids = [row.get("element_id") for row in compact["body"]["elements"] if row.get("tag") == "button"]
    assert button_ids == ["view_pm_comparison_report", "view_report"]


def _product(name: str, price: int, sales: int, choice: str, usage: str, purchase_reason: str | None) -> dict[str, object]:
    purchase = (
        {"核心购买理由": purchase_reason, "辅助购买理由": "影院和游戏体验", "core_tags": [purchase_reason], "_all_tags": [purchase_reason]}
        if purchase_reason
        else {"核心购买理由": "暂不能判断", "辅助购买理由": "暂不能判断", "core_tags": [], "_all_tags": []}
    )
    delivery = {"已形成稳定购买理由": purchase_reason} if purchase_reason else {}
    return {
        "name": name,
        "market": {
            "市场池口径": "65英寸 × 高价带",
            "均价": f"{price:,}元",
            "周均销量": f"{sales}台",
            "池内销量表现": "同池可比",
            "_price": price,
            "_weekly_sales": sales,
            "_pool_scope_key": "large_60_69|high",
        },
        "capabilities": {"亮度控光能力": "高亮度和多分区", "动态与游戏能力": "300Hz"},
        "choice_criteria": {"主要比较内容": choice, "其他比较内容": "游戏体育流畅", "_all_tags": [choice, "游戏体育流畅"]},
        "usage_needs": {"主要使用需求": usage, "其他使用需求": "体育赛事观看", "_all_tags": [usage, "体育赛事观看"]},
        "demand_audiences": {"主要吸引的需求型用户": "重视高端影音体验", "其他可覆盖用户": "经常观看体育或玩游戏", "_all_tags": ["重视高端影音体验", "经常观看体育或玩游戏"]},
        "message_reception": {
            "产品重点表达": "高亮画质和高刷新率",
            "用户正向感知": "高亮画质",
            "用户反向反馈": "当前未识别到稳定反向反馈",
            "尚需确认的表达": "当前未识别到需确认表达",
            "fact_tags": ["高亮画质", "高刷新率"],
            "supported_tags": ["高亮画质"],
            "contradicted_tags": [],
            "_all_tags": ["高亮画质", "高刷新率"],
        },
        "purchase_reasons": purchase,
        "value_delivery": delivery,
        "overview": {
            "价格和周均销量": f"{price:,}元；周均{sales}台",
            "产品事实最突出的部分": "高亮画质和300Hz",
            "主要承接的用户选择": choice,
            "用户主要使用需求": usage,
            "用户已经形成的购买理由": purchase_reason or "暂不能判断",
            "卖点接收情况": "高亮画质已被用户感知",
        },
    }


def _competitor() -> dict[str, object]:
    profile = {
        "found": True,
        "core_reasons_cn": ["画质配置解释加价"],
        "supporting_reasons_cn": ["游戏设备适配更安心"],
        "weak_expression_reasons_cn": [],
        "risk_drag_reasons_cn": [],
        "anchors": [
            {
                "anchor_cn": "画质配置解释加价",
                "role": "core_payment",
                "evidence_strength": "strong",
                "evidence_domains": ["param_fact", "fact_claim", "comment_perception"],
            }
        ],
    }
    return {
        "candidate": {
            "sku_code": "TV_COMPETITOR",
            "brand_name": "创维",
            "model_name": "65A7H PRO",
            "screen_size_inch": 65,
            "size_tier": "large_60_69",
            "price_band_in_size_tier": "mid_high",
            "price_wavg": 5637,
            "avg_weekly_sales_volume": 217,
            "price_gap_pct_to_target": -0.05,
        },
        "semantic_overlap": {},
        "param_claim_overlap": {},
        "sales_overlap": {},
        "candidate_fact_brief": {"sections": {}},
        "value_anchor": {
            "score": 0.8,
            "anchor_substitutability_score": 12,
            "shared_anchors": ["画质配置解释加价"],
            "target_stronger_anchors": ["高亮画质"],
            "candidate_stronger_anchors": ["家装融合"],
            "primary_direct_eligible": True,
        },
        "replacement_pressure": {
            "score": 0.8,
            "replacement_pressure_score": 8,
            "replacement_pressure_level": "high",
            "strong_pressure_allowed": True,
            "requires_review": False,
            "type": "value_substitution",
            "type_cn": "价值替代压力",
            "reason_cn": "覆盖本品核心购买理由。",
        },
        "target_purchase_reason_profile": profile,
        "candidate_purchase_reason_profile": profile,
    }
