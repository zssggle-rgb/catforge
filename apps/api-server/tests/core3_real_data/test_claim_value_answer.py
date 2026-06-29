from __future__ import annotations

from app.services.core3_real_data.analyst.claim_value_answer import build_claim_value_answer, render_claim_value_report


def _target() -> dict:
    return {"sku_code": "TV00029112", "brand_name": "海信", "model_name": "65E7Q"}


def _payload() -> dict:
    return {
        "method_note_cn": "测试口径说明。",
        "sku_level_claim_values": [
            {
                "claim_code": "tv_claim_hdr_high_brightness",
                "claim_name": "HDR/高亮画质",
                "business_claim_type_cn": "高溢价卖点",
                "target_has_claim": True,
                "claim_source_type_cn": "本品已成立卖点",
                "sku_level_user_payment_value_abs": 41,
                "sku_level_weekly_sales_lift_abs": 3.7,
                "main_contexts": ["高端画质升级战场"],
                "evidence_summary_cn": "参数强、评论强、市场承接成立。",
                "parameter_competitiveness": {
                    "overall_parameter_competitiveness_score": 91,
                    "overall_parameter_competitiveness_level_cn": "领先优势",
                    "explanation_cn": "亮度参数在同战场可比池中领先。",
                    "key_param_results": [
                        {
                            "source_param_code": "declared_brightness_nit_or_band",
                            "target_value": 5200,
                            "level_cn": "领先优势",
                        }
                    ],
                },
                "context_values": [
                    {
                        "context_name": "高端画质升级战场",
                        "price_premium_abs": 41,
                        "weekly_sales_lift_abs": 3.7,
                        "parameter_competitiveness": {
                            "overall_parameter_competitiveness_score": 91,
                            "overall_parameter_competitiveness_level_cn": "领先优势",
                        },
                    }
                ],
            },
            {
                "claim_code": "tv_claim_chip_performance",
                "claim_name": "芯片/处理器性能",
                "business_claim_type_cn": "人无我有型支付价值卖点",
                "target_has_claim": True,
                "claim_source_type_cn": "本品已成立卖点",
                "sku_level_user_payment_value_abs": 0,
                "sku_level_weekly_sales_lift_abs": 0,
                "main_contexts": ["高端画质升级战场"],
                "evidence_summary_cn": "本品芯片参数领先，但同战场缺少稳定对照样本。",
                "parameter_competitiveness": {
                    "overall_parameter_competitiveness_score": 92,
                    "overall_parameter_competitiveness_level_cn": "领先优势",
                    "key_param_results": [
                        {
                            "source_param_code": "processor_chip_model",
                            "target_value": "MT9655",
                            "level_cn": "领先优势",
                        }
                    ],
                },
                "context_values": [
                    {
                        "context_name": "高端画质升级战场",
                        "unique_payment_potential_scorecard": {
                            "total_score": 82,
                            "potential_level_cn": "高潜力",
                            "no_amount_reason_cn": "目标 SKU 是有卖点组唯一样本，不能用组间价差量化本品卖点金额。",
                            "verification_required_cn": "需要后续观察竞品跟进、评论和市场承接。",
                        },
                    }
                ],
            },
            {
                "claim_code": "tv_claim_hdmi21_connectivity",
                "claim_name": "HDMI2.1 连接",
                "business_claim_type_cn": "门槛卖点",
                "target_has_claim": True,
                "claim_source_type_cn": "本品已成立卖点",
                "sku_level_user_payment_value_abs": 0,
                "sku_level_weekly_sales_lift_abs": 0,
                "main_contexts": ["游戏体育流畅战场"],
                "evidence_summary_cn": "同池普遍具备，属于入围能力。",
                "parameter_competitiveness": {
                    "overall_parameter_competitiveness_score": 45,
                    "overall_parameter_competitiveness_level_cn": "基础门槛",
                    "key_param_results": [
                        {
                            "source_param_code": "hdmi21_flag",
                            "target_value": True,
                            "level_cn": "基础门槛",
                        }
                    ],
                },
            },
            {
                "claim_code": "tv_claim_dolby_audio_video",
                "claim_name": "杜比/影音认证",
                "business_claim_type_cn": "待激活卖点",
                "target_has_claim": True,
                "claim_source_type_cn": "本品已成立卖点",
                "sku_level_user_payment_value_abs": 0,
                "sku_level_weekly_sales_lift_abs": 0,
                "main_contexts": ["高端画质升级战场"],
                "evidence_summary_cn": "用户评论和市场验证不足。",
            },
            {
                "claim_code": "tv_claim_ai_large_model",
                "claim_name": "AI 大模型/智能能力",
                "business_claim_type_cn": "竞品拦截卖点",
                "target_has_claim": False,
                "claim_source_type_cn": "竞品拦截/机会缺口",
                "sku_level_user_payment_value_abs": 0,
                "sku_level_weekly_sales_lift_abs": 0,
                "main_contexts": ["智能互联体验战场"],
                "evidence_summary_cn": "竞品侧有表达，本品未形成已成立卖点。",
            },
        ],
        "claim_values": [
            {
                "claim_code": "tv_claim_hdr_high_brightness",
                "claim_name": "HDR/高亮画质",
                "business_claim_type_cn": "高溢价卖点",
                "target_has_claim": True,
                "context_type": "battlefield",
                "context_name": "高端画质升级战场",
                "pool_effect": {
                    "pool_claim_price_delta_abs": 1964,
                    "pool_claim_weekly_sales_delta_abs": -73,
                },
                "sku_excess_explanation": {
                    "sku_excess_price_explained_abs": 41,
                    "sku_excess_weekly_sales_explained_abs": 3.7,
                },
            },
            {
                "claim_code": "tv_claim_chip_performance",
                "claim_name": "芯片/处理器性能",
                "business_claim_type_cn": "人无我有型支付价值卖点",
                "target_has_claim": True,
                "context_type": "battlefield",
                "context_name": "高端画质升级战场",
                "pool_effect": {
                    "pool_claim_price_delta_abs": 1533,
                    "pool_claim_weekly_sales_delta_abs": -71,
                },
                "sku_excess_explanation": {},
                "supporting_dimensions": {
                    "unique_payment_potential_scorecard": {
                        "total_score": 82,
                        "potential_level_cn": "高潜力",
                        "no_amount_reason_cn": "目标 SKU 是有卖点组唯一样本，不能用组间价差量化本品卖点金额。",
                        "verification_required_cn": "需要后续观察竞品跟进、评论和市场承接。",
                    }
                },
            },
            {
                "claim_code": "tv_claim_hdmi21_connectivity",
                "claim_name": "HDMI2.1 连接",
                "business_claim_type_cn": "门槛卖点",
                "target_has_claim": True,
                "context_type": "battlefield",
                "context_name": "游戏体育流畅战场",
                "pool_effect": {
                    "pool_claim_price_delta_abs": -689,
                    "pool_claim_weekly_sales_delta_abs": -80.3,
                },
                "sku_excess_explanation": {},
            },
        ],
    }


def test_render_claim_value_report_separates_premium_and_threshold_claims() -> None:
    markdown = render_claim_value_report(title="海信 65E7Q 用户卖点价值分析报告", target=_target(), payload=_payload())

    assert "# 海信 65E7Q 用户卖点价值分析报告" in markdown
    assert "## 二、本品已成立卖点价值总榜" in markdown
    assert "| HDR/高亮画质 | 本品已成立卖点 | 高溢价卖点 | 高端画质升级战场 | 领先优势（91分）；关键参数：declared_brightness_nit_or_band=5200（领先优势） | 41元 | 3.7台/周 |" in markdown
    assert "| 芯片/处理器性能 | 本品已成立卖点 | 人无我有型支付价值卖点 | 高端画质升级战场 | 领先优势（92分）；关键参数：processor_chip_model=MT9655（领先优势） | 不作为正向量化 | 不作为正向量化 |" in markdown
    assert "## 四、人无我有型支付价值卖点" in markdown
    assert "高潜力（82分）" in markdown
    assert "目标 SKU 是有卖点组唯一样本" in markdown
    assert "| HDMI2.1 连接 | 本品已成立卖点 | 门槛卖点 | 游戏体育流畅战场 | 基础门槛（45分）；关键参数：hdmi21_flag=True（基础门槛） | 不作为正向量化 | 不作为正向量化 |" in markdown
    assert "| 卖点 | 业务分类 | 本品可解释金额/潜力等级 | 本品可解释销量 | 参数竞争力 | 证据说明 |" in markdown
    assert "| HDR/高亮画质 | 高溢价卖点 | 41元 | 3.7台/周 |" in markdown
    assert "| 芯片/处理器性能 | 人无我有型支付价值卖点 | 高潜力（82分） | 暂不量化 |" in markdown
    assert "可比池价格差异" not in markdown
    assert "1964元" not in markdown
    assert "1533元" not in markdown
    assert "原始组间差只作为评分和复核输入" in markdown
    assert "参数竞争力：亮度参数在同战场可比池中领先" in markdown
    assert "## 七、竞品拦截与机会缺口" in markdown
    assert "AI 大模型/智能能力" in markdown
    assert "不是本品当前已成立卖点" in markdown
    assert "可解释金额和可解释销量是基于可比市场池、价值战场权重和证据强度得到的解释性分摊" in markdown


def test_build_claim_value_answer_writes_markdown_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CATFORGE_ANALYST_REPORT_DIR", str(tmp_path))

    answer = build_claim_value_answer(
        target=_target(),
        payload=_payload(),
        with_report="markdown",
        max_chat_chars=500,
    )

    report = answer["report"]
    assert report["status"] == "markdown_ready"
    assert report["markdown_path"]
    assert f"详细报告：{report['markdown_path']}" in answer["short_answer"]
    saved = tmp_path.joinpath(report["markdown_path"].split("/")[-1]).read_text(encoding="utf-8")
    assert "HDR/高亮画质" in saved
    assert answer["markdown"] == saved


def test_feishu_doc_mode_does_not_return_local_markdown_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CATFORGE_ANALYST_REPORT_DIR", str(tmp_path))
    monkeypatch.delenv("CATFORGE_ANALYST_REPORT_PUBLISHER", raising=False)

    answer = build_claim_value_answer(
        target=_target(),
        payload=_payload(),
        with_report="feishu-doc",
        max_chat_chars=800,
    )

    report = answer["report"]
    assert report["status"] == "disabled"
    assert report["markdown_path"]
    assert report["markdown_path"] not in answer["short_answer"]
    assert "飞书文档未生成：飞书报告发布器未启用。" in answer["short_answer"]
