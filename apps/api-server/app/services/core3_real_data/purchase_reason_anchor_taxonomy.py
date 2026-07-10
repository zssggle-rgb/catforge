"""Versioned standard value-theme and purchase-reason taxonomy for M12D."""

from __future__ import annotations

from app.services.core3_real_data.constants import (
    CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
    CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
    M12DEvidenceDomain,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DAnchorEvidencePattern,
    M12DAnchorTaxonomy,
    M12DStandardPurchaseReasonDefinition,
    M12DStandardValueThemeDefinition,
)


class M12DAnchorTaxonomyNotFoundError(ValueError):
    pass


class M12DAnchorTaxonomyLoader:
    def load(self, taxonomy_version: str, *, product_category: str) -> M12DAnchorTaxonomy:
        normalized_category = product_category.strip().upper()
        if normalized_category == "TV" and taxonomy_version == CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION:
            return tv_purchase_reason_anchor_taxonomy_v0_1()
        if normalized_category == "AC" and taxonomy_version == CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION:
            return ac_purchase_reason_anchor_taxonomy_v0_1()
        raise M12DAnchorTaxonomyNotFoundError(
            f"M12D anchor taxonomy not found for {product_category}/{taxonomy_version}"
        )


def ac_purchase_reason_anchor_taxonomy_v0_1() -> M12DAnchorTaxonomy:
    capacity_patterns = _ac_capacity_patterns()
    energy_patterns = _ac_energy_patterns()
    quiet_patterns = _ac_quiet_patterns()
    airflow_health_patterns = _ac_airflow_health_patterns()
    large_space_patterns = _ac_large_space_patterns()
    install_patterns = _ac_install_patterns()
    operation_patterns = _ac_operation_patterns()
    budget_patterns = _ac_budget_patterns()
    seasonal_patterns = _ac_seasonal_patterns()
    dehumid_patterns = _ac_dehumid_patterns()

    return M12DAnchorTaxonomy(
        taxonomy_version=CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        product_category="AC",
        product_category_label_cn="空调",
        source_note_cn=(
            "AC 标准 taxonomy 由 Codex/业务基于 G01 上游证据审计、G02 候选报告和 G03 人审草案固化；"
            "价值主题表达用户可感知价值类型，购买理由表达用户选择 SKU 的决策逻辑；"
            "运行时程序只做证据匹配和候选门槛判断，不自动生成标准锚点族。"
        ),
        value_themes=[
            _value_theme(
                "cooling_heating_capacity_assurance",
                "冷暖能力确定感",
                "cooling_heating_capacity",
                "冷暖能力",
                "用户相信这台空调能覆盖目标空间，冷得快、热得稳，不容易买小或不够用。",
                10,
                capacity_patterns,
            ),
            _value_theme(
                "energy_cost_efficiency",
                "长期用电成本效率",
                "energy_cost",
                "长期电费",
                "用户相信长期使用电费更可控，能效、APF 和变频可以解释后续成本。",
                20,
                energy_patterns,
            ),
            _value_theme(
                "sleep_quiet_comfort",
                "睡眠静音舒适感",
                "sleep_quiet",
                "睡眠静音",
                "用户在卧室或夜间使用时更安静、不扰眠、温控更舒适。",
                30,
                quiet_patterns,
            ),
            _value_theme(
                "comfortable_airflow_health",
                "舒适风与健康空气",
                "airflow_health",
                "舒适健康空气",
                "用户减少直吹、闷、异味或空气健康担忧。",
                40,
                airflow_health_patterns,
            ),
            _value_theme(
                "large_space_coverage",
                "大空间覆盖感",
                "large_space",
                "大空间覆盖",
                "用户相信客厅、大卧室或大面积空间能被快速覆盖。",
                50,
                large_space_patterns,
            ),
            _value_theme(
                "installation_space_fit",
                "安装与空间适配",
                "installation_space_fit",
                "安装适配",
                "用户相信房型、安装位置和预算条件下能装得下、用得上。",
                60,
                install_patterns,
            ),
            _value_theme(
                "operation_maintenance_convenience",
                "操作维护省心",
                "operation_maintenance",
                "操作维护",
                "用户减少清洁、控制、调温和日常维护成本。",
                70,
                operation_patterns,
            ),
            _value_theme(
                "budget_configuration_efficiency",
                "预算配置效率",
                "budget_configuration",
                "预算配置",
                "用户在预算内获得足够的核心冷暖、能效或舒适配置。",
                80,
                budget_patterns,
            ),
            _value_theme(
                "seasonal_reliability",
                "季节和极端天气可靠性",
                "seasonal_reliability",
                "季节可靠",
                "用户相信夏季高温、冬季低温、梅雨潮湿等季节压力下更稳定。",
                90,
                seasonal_patterns,
            ),
        ],
        purchase_reasons=[
            _purchase_reason(
                "room_size_capacity_match_reduces_risk",
                "匹数空间匹配降低买小风险",
                "capacity_match",
                "匹数空间匹配",
                ["cooling_heating_capacity_assurance", "installation_space_fit"],
                "用户通过匹数、能力和空间任务判断这台空调不容易买小或不够用。",
                "需要能力参数或安装形态 + 空间/任务/市场参照。",
                "只有型号或匹数字样，不足以成为核心购买理由。",
                "这个 SKU 是否能降低用户买小、买错空间的风险？",
                10,
                [*capacity_patterns, *install_patterns],
                [
                    [M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM],
                    [M12DEvidenceDomain.SEMANTIC_SCENE, M12DEvidenceDomain.COMMENT_PERCEPTION, M12DEvidenceDomain.MARKET_ACCEPTANCE],
                ],
            ),
            _purchase_reason(
                "large_space_one_step_cooling_heating",
                "大空间冷暖一步到位",
                "large_space",
                "大空间冷暖",
                ["large_space_coverage", "cooling_heating_capacity_assurance"],
                "面向客厅或大空间，SKU 用大匹数、柜机/大风量和市场承接解释一步到位。",
                "需要大空间任务 + 能力/柜机事实 + 评论或市场承接。",
                "只有柜机或大匹数标签时不能强判。",
                "这个 SKU 是否能解释大空间冷暖为什么一步到位？",
                20,
                [*large_space_patterns, *capacity_patterns],
                [
                    [M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM],
                    [M12DEvidenceDomain.SEMANTIC_SCENE, M12DEvidenceDomain.COMMENT_PERCEPTION, M12DEvidenceDomain.MARKET_ACCEPTANCE],
                ],
            ),
            _purchase_reason(
                "cooling_heating_performance_justifies_price",
                "冷暖效果解释更高价格",
                "price_justification",
                "冷暖加价解释",
                ["cooling_heating_capacity_assurance", "seasonal_reliability"],
                "在中高/高价格位置，SKU 用冷暖能力、稳定性和用户感知解释更高价格。",
                "需要高价格位置 + 冷暖能力事实 + 评论、M12C 或市场承接。",
                "只有高价或能力口号，没有体验/市场补证时不能成立。",
                "这个 SKU 的冷暖效果是否足以解释更高价格？",
                30,
                [*capacity_patterns, *seasonal_patterns, _ac_mid_high_market_pattern()],
                [
                    [M12DEvidenceDomain.MARKET_ACCEPTANCE],
                    [M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM],
                    [M12DEvidenceDomain.COMMENT_PERCEPTION, M12DEvidenceDomain.CLAIM_VALUE],
                ],
            ),
            _purchase_reason(
                "long_term_energy_saving_offsets_price",
                "长期省电抵消更高价格",
                "energy_cost",
                "长期省电",
                ["energy_cost_efficiency", "budget_configuration_efficiency"],
                "用户愿意为高能效多花钱，因为长期省电可以解释使用成本。",
                "需要能效/APF 事实 + 长期使用任务或省电评论 + 价格位置/M12C 补证。",
                "只有一级能效口号时封顶弱表达。",
                "这个 SKU 是否能解释长期省电抵消更高价格？",
                40,
                [*energy_patterns, _ac_mid_high_market_pattern()],
                [[M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM, M12DEvidenceDomain.COMMENT_PERCEPTION, M12DEvidenceDomain.CLAIM_VALUE]],
            ),
            _purchase_reason(
                "same_price_efficiency_capacity_gain",
                "同价位能效/能力获得感",
                "budget_configuration",
                "同价位获得感",
                ["budget_configuration_efficiency", "energy_cost_efficiency", "cooling_heating_capacity_assurance"],
                "在同价位池里，SKU 用能效、冷暖能力或销量承接解释选它更划算。",
                "需要价格/市场证据 + 能效或能力事实；只有性价比表达不够。",
                "只有 price_value、补贴或低价表达时封顶弱表达。",
                "这个 SKU 是否在同价位中提供更可解释的能效/能力获得感？",
                50,
                [*budget_patterns, *energy_patterns, *capacity_patterns],
                [[M12DEvidenceDomain.CLAIM_POSITION, M12DEvidenceDomain.MARKET_ACCEPTANCE, M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM]],
            ),
            _purchase_reason(
                "low_price_core_ac_experience_intact",
                "低价不明显牺牲核心冷暖体验",
                "budget_configuration",
                "低价核心体验",
                ["budget_configuration_efficiency", "cooling_heating_capacity_assurance"],
                "在低/中低价位置，SKU 用冷暖能力、能效、评论或销量证明低价不是明显牺牲核心体验。",
                "需要低价位置 + 冷暖/能效事实或评论/销量承接。",
                "只有低价、补贴或 price_value 表达时，不能进入核心产品理由。",
                "这个 SKU 是否能解释低价下核心冷暖体验仍然够用？",
                60,
                [*budget_patterns, *capacity_patterns, *energy_patterns, _ac_low_market_pattern()],
                [
                    [M12DEvidenceDomain.CLAIM_POSITION, M12DEvidenceDomain.MARKET_ACCEPTANCE],
                    [M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM, M12DEvidenceDomain.COMMENT_PERCEPTION, M12DEvidenceDomain.CLAIM_VALUE],
                ],
            ),
            _purchase_reason(
                "sleep_room_quiet_comfort_assurance",
                "卧室睡眠更安静舒适",
                "sleep_quiet",
                "卧室睡眠",
                ["sleep_quiet_comfort", "comfortable_airflow_health"],
                "卧室睡眠场景下，SKU 用低噪、睡眠模式、风感和评论证明更安静舒适。",
                "需要静音/风感事实 + 卧室/睡眠任务或评论。",
                "只有静音卖点，没有噪音参数、任务或评论时封顶辅助/弱表达。",
                "这个 SKU 是否能解释卧室睡眠更安静舒适？",
                70,
                quiet_patterns,
                [[M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM, M12DEvidenceDomain.COMMENT_PERCEPTION, M12DEvidenceDomain.SEMANTIC_SCENE]],
            ),
            _purchase_reason(
                "elderly_child_soft_wind_comfort",
                "老人儿童房柔风不直吹",
                "airflow_health",
                "柔风不直吹",
                ["comfortable_airflow_health", "sleep_quiet_comfort"],
                "老人儿童或家庭舒适场景下，柔风、防直吹和风感评论降低不适风险。",
                "需要柔风/防直吹事实 + 老人儿童/卧室任务或风感评论。",
                "只有柔风或防直吹表达，缺场景/评论时封顶辅助。",
                "这个 SKU 是否能解释老人儿童房柔风不直吹？",
                80,
                _ac_soft_wind_patterns(),
                [[M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM, M12DEvidenceDomain.COMMENT_PERCEPTION, M12DEvidenceDomain.SEMANTIC_SCENE]],
            ),
            _purchase_reason(
                "fresh_air_health_reduces_stuffy_risk",
                "新风/净化减少闷和空气担忧",
                "airflow_health",
                "新风健康空气",
                ["comfortable_airflow_health", "operation_maintenance_convenience"],
                "用户用新风、净化或除菌能力降低室内闷、异味和空气健康担忧。",
                "需要新风/净化参数或事实 + 空气评论/任务或 M12C。",
                "只有新风/净化口号，没有风量/滤网/评论时封顶弱表达。",
                "这个 SKU 是否能解释减少闷和空气健康担忧？",
                90,
                _ac_fresh_air_patterns(),
                [[M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM, M12DEvidenceDomain.COMMENT_PERCEPTION, M12DEvidenceDomain.SEMANTIC_SCENE, M12DEvidenceDomain.CLAIM_VALUE]],
            ),
            _purchase_reason(
                "humidity_dehumidification_reassurance",
                "潮湿环境除湿更安心",
                "seasonal_reliability",
                "除湿安心",
                ["seasonal_reliability", "comfortable_airflow_health"],
                "梅雨或潮湿环境下，除湿和季节可靠性降低使用担忧。",
                "需要除湿能力或评论 + 季节/潮湿场景。",
                "只有除湿字样而无评论/场景补证时不能强判。",
                "这个 SKU 是否能解释潮湿环境除湿更安心？",
                100,
                dehumid_patterns,
                [[M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM, M12DEvidenceDomain.COMMENT_PERCEPTION, M12DEvidenceDomain.SEMANTIC_SCENE]],
            ),
            _purchase_reason(
                "self_cleaning_reduces_maintenance_risk",
                "自清洁/防霉降低维护风险",
                "operation_maintenance",
                "维护省心",
                ["operation_maintenance_convenience", "comfortable_airflow_health"],
                "用户通过自清洁、防霉和维护便利降低清洁、异味和长期维护风险。",
                "需要自清洁/防霉事实 + 维护评论或健康空气场景。",
                "只有自清洁口号时封顶辅助/弱表达。",
                "这个 SKU 是否能解释自清洁/防霉降低维护风险？",
                110,
                _ac_self_clean_patterns(),
                [[M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM, M12DEvidenceDomain.COMMENT_PERCEPTION, M12DEvidenceDomain.SEMANTIC_SCENE]],
            ),
            _purchase_reason(
                "small_room_installation_fit",
                "小房间/租房安装适配",
                "installation_space_fit",
                "小房间安装",
                ["installation_space_fit", "budget_configuration_efficiency"],
                "小房间、租房或安装受限场景下，SKU 用挂机/小匹数/价格和安装适配降低选择摩擦。",
                "需要安装/小空间事实 + 租房/小房间任务或低价市场承接。",
                "只有安装服务或低价时不能强判。",
                "这个 SKU 是否能解释小房间/租房安装更适配？",
                120,
                [*install_patterns, *budget_patterns, _ac_low_market_pattern()],
                [[M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM, M12DEvidenceDomain.SEMANTIC_SCENE, M12DEvidenceDomain.MARKET_ACCEPTANCE]],
            ),
            _purchase_reason(
                "smart_remote_control_less_friction",
                "远程/智能控制减少操作摩擦",
                "operation_maintenance",
                "智能控制",
                ["operation_maintenance_convenience"],
                "用户通过 App、远程、语音或智能控制减少日常操作成本。",
                "需要智能/远程事实 + 评论或智能任务补证。",
                "只有智能口号时封顶弱表达。",
                "这个 SKU 是否能解释远程/智能控制减少操作摩擦？",
                130,
                _ac_smart_control_patterns(),
                [[M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM, M12DEvidenceDomain.COMMENT_PERCEPTION, M12DEvidenceDomain.SEMANTIC_SCENE, M12DEvidenceDomain.CLAIM_VALUE]],
            ),
        ],
    )


def tv_purchase_reason_anchor_taxonomy_v0_1() -> M12DAnchorTaxonomy:
    picture_patterns = _picture_patterns()
    dynamic_patterns = _dynamic_patterns()
    immersion_patterns = _immersion_patterns()
    budget_patterns = _budget_patterns()
    comfort_patterns = _comfort_patterns()
    operation_patterns = _operation_patterns()
    aesthetic_patterns = _aesthetic_patterns()

    return M12DAnchorTaxonomy(
        taxonomy_version=CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
        product_category="TV",
        product_category_label_cn="彩电",
        source_note_cn=(
            "TV 标准 taxonomy 由 Codex/业务基于 G04R1 候选报告固化为两层结构："
            "价值主题表达用户可感知价值类型，购买理由表达用户选择 SKU 的决策逻辑；"
            "运行时程序只做证据匹配和候选门槛判断，不自动生成标准锚点族。"
        ),
        value_themes=[
            _value_theme(
                "picture_upgrade_perception",
                "画质升级感",
                "picture_upgrade",
                "画质升级",
                "用户能感知到画面清晰度、亮度、控光、色彩或显示技术升级。",
                10,
                picture_patterns,
            ),
            _value_theme(
                "dynamic_stability_perception",
                "动态画面稳定感",
                "dynamic_stability",
                "动态稳定",
                "游戏、体育、运动画面中流畅、低延迟、少拖影的体验获得感。",
                20,
                dynamic_patterns,
            ),
            _value_theme(
                "living_room_immersion_perception",
                "客厅沉浸感",
                "living_room_immersion",
                "客厅沉浸",
                "大屏、音效、杜比、观影距离与客厅空间共同形成的沉浸感。",
                30,
                immersion_patterns,
            ),
            _value_theme(
                "budget_configuration_efficiency",
                "预算配置效率",
                "budget_configuration",
                "预算配置",
                "在给定预算和尺寸池里，用户获得核心配置、价格和销量承接的效率。",
                40,
                budget_patterns,
            ),
            _value_theme(
                "long_watch_comfort_perception",
                "长看舒适感",
                "long_watch_comfort",
                "长看舒适",
                "护眼、低蓝光、无频闪、抗反光和家庭长时间观看形成的舒适安心。",
                50,
                comfort_patterns,
            ),
            _value_theme(
                "operation_convenience_perception",
                "操作便利感",
                "operation_convenience",
                "操作便利",
                "AI、语音、投屏、IoT、系统易用带来的家庭使用便利。",
                60,
                operation_patterns,
            ),
            _value_theme(
                "space_aesthetic_fit",
                "空间审美适配",
                "space_aesthetic",
                "空间审美",
                "外观、超薄、贴墙、全面屏、壁画和新家装修的空间适配价值。",
                70,
                aesthetic_patterns,
            ),
        ],
        purchase_reasons=[
            _purchase_reason(
                "picture_upgrade_justifies_price",
                "画质配置解释加价",
                "picture_upgrade",
                "画质升级付费",
                ["picture_upgrade_perception"],
                "在中高价或同尺寸对比中，SKU 用可验证画质配置和用户感知解释更高价格。",
                "需要画质事实证据 + 用户感知或 M12C 支付价值 + 价格/市场位置。",
                "只有高端画质口号或单一 claim 时不能成立。",
                "这个 SKU 的画质配置是否足以解释它的价格？",
                10,
                [*picture_patterns, _mid_high_market_pattern()],
                [
                    [M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM],
                    [M12DEvidenceDomain.COMMENT_PERCEPTION, M12DEvidenceDomain.CLAIM_VALUE],
                    [M12DEvidenceDomain.MARKET_ACCEPTANCE],
                ],
            ),
            _purchase_reason(
                "low_price_core_experience_intact",
                "低价不明显牺牲核心体验",
                "budget_configuration",
                "预算配置",
                ["budget_configuration_efficiency", "picture_upgrade_perception", "operation_convenience_perception"],
                "在低/中低价格位置，SKU 用核心画质、尺寸、系统或评论满意度证明低价不是明显牺牲体验。",
                "需要低/中低价格位置 + 至少一个核心体验证据；销量或评论正向可强化。",
                "只有低价、补贴或促销表达时，不进入产品购买理由。",
                "这个 SKU 是否能解释低价下核心体验仍然够用？",
                20,
                [*budget_patterns, *_core_experience_patterns(), _low_market_pattern()],
                [[M12DEvidenceDomain.MARKET_ACCEPTANCE], [M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.COMMENT_PERCEPTION]],
            ),
            _purchase_reason(
                "same_price_core_config_gain",
                "同价位核心配置获得感",
                "budget_configuration",
                "预算配置",
                ["budget_configuration_efficiency", "picture_upgrade_perception", "dynamic_stability_perception"],
                "在同尺寸/同价位池中，SKU 用更多核心配置或销量承接解释选它更划算。",
                "需要价格/市场证据 + 配置事实或评论价值感；厂家性价比表达只能弱支撑。",
                "只有 value_price/price_value 时封顶弱表达。",
                "这个 SKU 是否在同价位中提供了更可解释的核心配置获得感？",
                30,
                [*budget_patterns, *_core_experience_patterns()],
                [[M12DEvidenceDomain.CLAIM_POSITION, M12DEvidenceDomain.MARKET_ACCEPTANCE]],
            ),
            _purchase_reason(
                "same_size_picture_step_up",
                "同尺寸画质越级获得感",
                "picture_upgrade",
                "画质升级付费",
                ["picture_upgrade_perception", "budget_configuration_efficiency"],
                "在同尺寸池中，SKU 用更强画质配置形成越级获得感。",
                "需要同尺寸/价格池参照 + 画质事实证据；评论或 M12C 可作为强化。",
                "只有 MiniLED/画质口号但没有同尺寸参照或体验证据时，只能弱支撑。",
                "这个 SKU 是否在同尺寸里提供了更强画质获得感？",
                40,
                [*picture_patterns, _size_market_pattern()],
                [[M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM], [M12DEvidenceDomain.MARKET_ACCEPTANCE]],
            ),
            _purchase_reason(
                "worth_paying_more_for_experience_upgrade",
                "贵得值的体验升级",
                "premium_upgrade",
                "贵得值",
                [
                    "picture_upgrade_perception",
                    "dynamic_stability_perception",
                    "living_room_immersion_perception",
                ],
                "在中高/高价格位置，SKU 让用户看到多花钱换来的画质、动态或沉浸升级，并由评论、M12C 或市场承接证明这笔加价值得。",
                "需要中高/高价格位置 + 至少一个可感知强体验证据 + 评论、M12C 或市场承接；若反馈反向则转为价格压力。",
                "只有高端口号、品牌溢价或参数堆叠，用户感知不到升级时，不能作为正向购买理由。",
                "用户是否会觉得这个 SKU 虽然更贵，但多花的钱换来了明确体验升级？",
                50,
                [*picture_patterns, *dynamic_patterns, *immersion_patterns, _mid_high_market_pattern()],
                [
                    [M12DEvidenceDomain.MARKET_ACCEPTANCE],
                    [M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM],
                    [M12DEvidenceDomain.COMMENT_PERCEPTION, M12DEvidenceDomain.CLAIM_VALUE],
                ],
            ),
            _purchase_reason(
                "av_user_willing_to_pay_for_picture",
                "影音用户愿为画质升级付费",
                "picture_upgrade",
                "画质升级付费",
                ["picture_upgrade_perception", "living_room_immersion_perception"],
                "影音用户因画质、控光、亮度或观影体验升级而愿意多付钱。",
                "需要画质事实 + 观影/影音任务或评论 + M12C 正向支付价值。",
                "只有影音/影院宣传语，缺少画质事实或 M12C 时不能强判。",
                "影音用户是否愿意为这个 SKU 的画质升级付费？",
                60,
                [*picture_patterns, *_av_semantic_patterns()],
                [[M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM], [M12DEvidenceDomain.SEMANTIC_SCENE, M12DEvidenceDomain.COMMENT_PERCEPTION]],
            ),
            _purchase_reason(
                "gaming_device_fit_reduces_risk",
                "游戏设备适配降低踩坑风险",
                "dynamic_stability",
                "游戏流畅",
                ["dynamic_stability_perception"],
                "SKU 用高刷、接口、低延迟和游戏场景证据降低用户买错游戏电视的风险。",
                "需要高刷/接口/低延迟事实证据 + 游戏任务或评论感知。",
                "只有游戏电视表达时不能成立。",
                "这个 SKU 是否能降低游戏设备适配踩坑风险？",
                70,
                dynamic_patterns,
                [[M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM], [M12DEvidenceDomain.SEMANTIC_SCENE, M12DEvidenceDomain.COMMENT_PERCEPTION]],
            ),
            _purchase_reason(
                "sports_motion_stability",
                "体育/运动画面流畅更稳",
                "dynamic_stability",
                "体育运动",
                ["dynamic_stability_perception"],
                "体育和运动画面用户因高刷、MEMC 或流畅评论而认为画面更稳。",
                "需要刷新率/MEMC/高刷事实 + 体育或运动评论/任务支撑。",
                "只有高刷口号，没有体育/运动场景证据时不能强判。",
                "这个 SKU 是否能解释体育/运动画面看起来更稳？",
                80,
                dynamic_patterns,
                [[M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM], [M12DEvidenceDomain.SEMANTIC_SCENE, M12DEvidenceDomain.COMMENT_PERCEPTION]],
            ),
            _purchase_reason(
                "big_screen_cinema_substitution",
                "大屏影音替代影院感",
                "living_room_immersion",
                "客厅沉浸",
                ["living_room_immersion_perception", "picture_upgrade_perception"],
                "SKU 用大屏、音画和观影场景让用户获得接近影院的家庭影音体验。",
                "需要大屏/音画事实 + 观影评论或影院沉浸任务；市场同尺寸承接可强化。",
                "只有影院级/沉浸感宣传语，没有音画事实或评论时不能成立。",
                "这个 SKU 是否能让用户觉得在家也有影院感？",
                90,
                immersion_patterns,
                [[M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM], [M12DEvidenceDomain.SEMANTIC_SCENE, M12DEvidenceDomain.COMMENT_PERCEPTION]],
            ),
            _purchase_reason(
                "living_room_upgrade_one_step",
                "客厅换新一步到位",
                "living_room_immersion",
                "客厅换新",
                ["living_room_immersion_perception", "picture_upgrade_perception"],
                "客厅换新时，SKU 通过尺寸、画质、观影任务和市场承接形成一步到位选择。",
                "需要尺寸/观影事实 + 用户任务或评论感知 + 市场承接。",
                "只有屏幕尺寸数字，不足以成为购买理由。",
                "这个 SKU 是否能解释客厅换新一步到位？",
                100,
                [*immersion_patterns, _size_market_pattern()],
                [[M12DEvidenceDomain.PARAM_FACT], [M12DEvidenceDomain.SEMANTIC_SCENE, M12DEvidenceDomain.COMMENT_PERCEPTION], [M12DEvidenceDomain.MARKET_ACCEPTANCE]],
            ),
            _purchase_reason(
                "family_long_watch_comfort_assurance",
                "家庭长时间观看更安心",
                "long_watch_comfort",
                "长看舒适",
                ["long_watch_comfort_perception"],
                "家庭长时间观看时，SKU 通过护眼参数、认证或评论降低观看负担担忧。",
                "需要护眼参数或认证 + 评论/任务支撑；泛健康口号不足。",
                "只有健康宣传或认证口号时不能强判。",
                "这个 SKU 是否能让家庭长时间观看更安心？",
                110,
                comfort_patterns,
                [[M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM]],
            ),
            _purchase_reason(
                "family_operation_less_friction",
                "家庭多设备使用更省操作",
                "operation_convenience",
                "操作便利",
                ["operation_convenience_perception"],
                "家庭多人多设备使用时，SKU 用投屏、语音、IoT 和系统易用降低操作成本。",
                "需要智能/互联事实证据 + 任务或评论易用感知。",
                "只有 AI 或智能口号时只能弱支撑。",
                "这个 SKU 是否能解释家庭日常使用更省操作？",
                120,
                operation_patterns,
                [[M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM]],
            ),
            _purchase_reason(
                "new_home_aesthetic_fit",
                "新家客厅审美适配",
                "space_aesthetic",
                "空间审美",
                ["space_aesthetic_fit"],
                "新家和家装场景下，SKU 用外观、安装或空间适配形成购买理由。",
                "需要外观/安装事实 + 新家/家装任务或评论支撑。",
                "只有外观好看表达时不能直接成为核心购买理由。",
                "这个 SKU 是否能解释新家客厅审美适配？",
                130,
                aesthetic_patterns,
                [[M12DEvidenceDomain.PARAM_FACT, M12DEvidenceDomain.FACT_CLAIM]],
            ),
        ],
    )


def _ac_capacity_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M03B",
            M12DEvidenceDomain.PARAM_FACT,
            ["param_values_json"],
            ["capacity_hp", "cooling_capacity", "heating_capacity", "air_volume", "fan_air_volume"],
            ["匹", "制冷量", "制热量", "循环风量", "大风量", "速冷", "速热"],
            "参数事实显示冷暖能力和空间覆盖基础。",
        ),
        _pattern(
            "M04C",
            M12DEvidenceDomain.FACT_CLAIM,
            ["fact_claim_codes", "claim_codes", "dimension_profile_json", "claim_summary_json"],
            ["temperature_performance"],
            ["速冷", "速热", "制冷", "制热", "大风量", "冷暖"],
            "事实卖点指向冷暖能力，但单一厂家表达需封顶。",
            weak_expression_only=True,
        ),
        _pattern(
            "M05C",
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            ["dimension_summary_json", "signal_summary_json", "evidence_examples_json", "supported_param_codes", "supported_claim_codes"],
            ["temperature_performance", "cooling_heating", "room_size_match"],
            ["制冷快", "制热", "降温", "暖和", "够用", "风量", "房间"],
            "评论感知支持冷暖能力和房间匹配。",
        ),
        _pattern(
            "M09C_M10C_M11C",
            M12DEvidenceDomain.SEMANTIC_SCENE,
            ["user_task", "target_group", "battlefield", "user_task_summary_json", "battlefield_summary_json"],
            ["large_space", "small_room", "capacity_match", "cooling_heating", "BF_COOLING_HEATING_CAPACITY"],
            ["大空间", "小房间", "卧室", "客厅", "冷暖", "空间"],
            "语义画像指向冷暖能力或空间匹配任务。",
        ),
        _pattern(
            "M12C",
            M12DEvidenceDomain.CLAIM_VALUE,
            ["claim_value_roles", "positive_claims_json", "claim_value_summary_json"],
            ["sales_driver_estimated", "temperature_performance"],
            ["销量转化", "sales_driver_estimated", "冷暖"],
            "M12C 显示冷暖能力相关卖点具备销量转化证据。",
        ),
    ]


def _ac_energy_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M03B",
            M12DEvidenceDomain.PARAM_FACT,
            ["param_values_json"],
            ["apf", "energy_efficiency_level", "inverter_flag"],
            ["APF", "一级能效", "能效", "变频", "省电"],
            "参数事实显示能效和长期用电成本基础。",
        ),
        _pattern(
            "M04C",
            M12DEvidenceDomain.FACT_CLAIM,
            ["fact_claim_codes", "claim_codes", "dimension_profile_json", "claim_summary_json"],
            ["energy_efficiency"],
            ["一级能效", "APF", "变频", "省电", "节能"],
            "事实卖点指向能效省电，但单一厂家表达需封顶。",
            weak_expression_only=True,
        ),
        _pattern(
            "M05C",
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            ["dimension_summary_json", "signal_summary_json", "evidence_examples_json"],
            ["energy_efficiency", "power_saving", "electricity_cost"],
            ["省电", "电费", "节能", "耗电"],
            "评论感知支持长期用电成本效率。",
        ),
        _pattern(
            "M09C_M10C_M11C",
            M12DEvidenceDomain.SEMANTIC_SCENE,
            ["user_task", "target_group", "battlefield", "battlefield_summary_json"],
            ["energy_cost_efficiency", "budget_sensitive", "BF_ENERGY_SAVING"],
            ["长期", "省电", "节能", "预算", "能效"],
            "语义画像指向长期用电或节能价值场景。",
        ),
        _pattern(
            "M12C",
            M12DEvidenceDomain.CLAIM_VALUE,
            ["claim_value_roles", "positive_claims_json", "claim_value_summary_json"],
            ["sales_driver_estimated", "energy_efficiency"],
            ["sales_driver_estimated", "省电", "能效"],
            "M12C 显示能效卖点具备销量转化证据。",
        ),
    ]


def _ac_quiet_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M03B",
            M12DEvidenceDomain.PARAM_FACT,
            ["param_values_json"],
            ["noise_db", "sleep_mode", "quiet_mode"],
            ["静音", "噪音", "低噪", "睡眠"],
            "参数事实显示低噪或睡眠模式。",
        ),
        _pattern(
            "M04C",
            M12DEvidenceDomain.FACT_CLAIM,
            ["fact_claim_codes", "claim_codes", "dimension_profile_json"],
            ["airflow_comfort", "quiet_sleep"],
            ["静音", "低噪", "睡眠"],
            "事实卖点指向静音睡眠，但单一厂家表达需封顶。",
            weak_expression_only=True,
        ),
        _pattern(
            "M05C",
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            ["dimension_summary_json", "signal_summary_json", "evidence_examples_json"],
            ["quiet_sleep", "noise", "bedroom"],
            ["安静", "噪音", "睡觉", "睡眠", "卧室", "不吵"],
            "评论感知支持卧室睡眠静音。",
        ),
        _pattern(
            "M09C_M10C_M11C",
            M12DEvidenceDomain.SEMANTIC_SCENE,
            ["user_task", "target_group", "battlefield"],
            ["bedroom_sleep", "quiet_comfort", "BF_SLEEP_QUIET"],
            ["卧室", "睡眠", "静音"],
            "语义画像指向卧室睡眠或静音舒适场景。",
        ),
    ]


def _ac_airflow_health_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        *_ac_soft_wind_patterns(),
        *_ac_fresh_air_patterns(),
    ]


def _ac_soft_wind_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M03B",
            M12DEvidenceDomain.PARAM_FACT,
            ["param_values_json"],
            ["soft_wind", "anti_direct_blow", "swing_mode", "wide_angle_airflow"],
            ["柔风", "防直吹", "扫风", "风感"],
            "参数事实显示柔风、防直吹或扫风能力。",
        ),
        _pattern(
            "M04C",
            M12DEvidenceDomain.FACT_CLAIM,
            ["fact_claim_codes", "claim_codes", "dimension_profile_json"],
            ["airflow_comfort"],
            ["柔风", "防直吹", "舒适风", "扫风"],
            "事实卖点指向舒适风，但单一厂家表达需封顶。",
            weak_expression_only=True,
        ),
        _pattern(
            "M05C",
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            ["dimension_summary_json", "signal_summary_json", "evidence_examples_json"],
            ["airflow_comfort", "anti_direct_blow"],
            ["不直吹", "柔风", "风感", "舒服", "老人", "孩子"],
            "评论感知支持柔风不直吹。",
        ),
        _pattern(
            "M09C_M10C_M11C",
            M12DEvidenceDomain.SEMANTIC_SCENE,
            ["user_task", "target_group", "battlefield"],
            ["elderly_child", "soft_wind", "airflow_comfort", "BF_AIRFLOW_COMFORT"],
            ["老人", "儿童", "孩子", "柔风", "防直吹"],
            "语义画像指向老人儿童或舒适风场景。",
        ),
    ]


def _ac_fresh_air_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M03B",
            M12DEvidenceDomain.PARAM_FACT,
            ["param_values_json"],
            ["fresh_air_volume", "filter_grade", "sterilization", "purification"],
            ["新风", "净化", "除菌", "滤网", "空气"],
            "参数事实显示新风、净化或除菌能力。",
        ),
        _pattern(
            "M04C",
            M12DEvidenceDomain.FACT_CLAIM,
            ["fact_claim_codes", "claim_codes", "dimension_profile_json"],
            ["health_clean_air"],
            ["新风", "净化", "除菌", "健康空气"],
            "事实卖点指向健康空气，但单一厂家表达需封顶。",
            weak_expression_only=True,
        ),
        _pattern(
            "M05C",
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            ["dimension_summary_json", "signal_summary_json", "evidence_examples_json"],
            ["health_clean_air", "fresh_air", "odor"],
            ["新风", "空气", "闷", "异味", "净化", "除菌"],
            "评论感知支持减少闷和空气担忧。",
        ),
        _pattern(
            "M09C_M10C_M11C",
            M12DEvidenceDomain.SEMANTIC_SCENE,
            ["user_task", "target_group", "battlefield"],
            ["health_clean_air", "fresh_air", "BF_HEALTH_CLEAN_AIR"],
            ["健康", "空气", "新风", "净化"],
            "语义画像指向健康空气场景。",
        ),
        _pattern(
            "M12C",
            M12DEvidenceDomain.CLAIM_VALUE,
            ["claim_value_roles", "positive_claims_json", "claim_value_summary_json"],
            ["sales_driver_estimated", "health_clean_air"],
            ["sales_driver_estimated", "新风", "健康空气"],
            "M12C 显示健康空气卖点具备销量转化证据。",
        ),
    ]


def _ac_large_space_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M03B",
            M12DEvidenceDomain.PARAM_FACT,
            ["param_values_json"],
            ["capacity_hp", "installation_type", "air_volume", "cooling_capacity"],
            ["3匹", "柜机", "72", "88", "大风量", "大空间"],
            "参数事实显示大匹数、柜机或大风量覆盖能力。",
        ),
        _pattern(
            "M04C",
            M12DEvidenceDomain.FACT_CLAIM,
            ["fact_claim_codes", "claim_codes", "dimension_profile_json"],
            ["temperature_performance"],
            ["大空间", "大风量", "客厅", "柜机"],
            "事实卖点指向大空间覆盖，但单一厂家表达需封顶。",
            weak_expression_only=True,
        ),
        _pattern(
            "M05C",
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            ["dimension_summary_json", "signal_summary_json", "evidence_examples_json"],
            ["large_space", "living_room", "air_volume"],
            ["客厅", "大空间", "大房间", "风量", "制冷快", "够用"],
            "评论感知支持大空间冷暖覆盖。",
        ),
        _pattern(
            "M09C_M10C_M11C",
            M12DEvidenceDomain.SEMANTIC_SCENE,
            ["user_task", "target_group", "battlefield"],
            ["large_space", "living_room", "BF_LARGE_SPACE_COVERAGE"],
            ["客厅", "大空间", "柜机"],
            "语义画像指向客厅或大空间覆盖任务。",
        ),
    ]


def _ac_install_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M03B",
            M12DEvidenceDomain.PARAM_FACT,
            ["param_values_json"],
            ["installation_type", "indoor_unit_size", "outdoor_unit_size", "wall_mount"],
            ["挂机", "柜机", "安装", "内机", "外机", "小房间"],
            "参数事实显示安装形态和空间适配基础。",
        ),
        _pattern(
            "M04C",
            M12DEvidenceDomain.SERVICE_SIGNAL,
            ["fact_claim_codes", "claim_codes", "dimension_profile_json"],
            ["installation_design", "service_fulfillment"],
            ["安装", "送装", "售后", "小巧"],
            "安装、送装或售后只能作为辅助或风险信号。",
            weak_expression_only=True,
        ),
        _pattern(
            "M05C",
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            ["dimension_summary_json", "signal_summary_json", "evidence_examples_json"],
            ["installation", "small_room", "renter"],
            ["安装", "空间", "小房间", "租房", "位置", "外机"],
            "评论感知支持安装和空间适配。",
        ),
        _pattern(
            "M09C_M10C_M11C",
            M12DEvidenceDomain.SEMANTIC_SCENE,
            ["user_task", "target_group", "battlefield"],
            ["small_room", "renter", "installation_space_fit", "BF_INSTALLATION_SPACE_FIT"],
            ["小房间", "租房", "安装", "空间"],
            "语义画像指向小房间、租房或安装适配场景。",
        ),
    ]


def _ac_operation_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        *_ac_smart_control_patterns(),
        *_ac_self_clean_patterns(),
    ]


def _ac_smart_control_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M03B",
            M12DEvidenceDomain.PARAM_FACT,
            ["param_values_json"],
            ["wifi", "app_control", "voice_control", "smart_control", "remote_control"],
            ["WiFi", "App", "语音", "智能", "远程"],
            "参数事实显示远程或智能控制能力。",
        ),
        _pattern(
            "M04C",
            M12DEvidenceDomain.FACT_CLAIM,
            ["fact_claim_codes", "claim_codes", "dimension_profile_json"],
            ["smart_control"],
            ["智能", "远程", "App", "语音"],
            "事实卖点指向智能控制，但单一厂家表达需封顶。",
            weak_expression_only=True,
        ),
        _pattern(
            "M05C",
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            ["dimension_summary_json", "signal_summary_json", "evidence_examples_json"],
            ["smart_control", "remote_control"],
            ["智能", "远程", "App", "语音", "控制", "方便"],
            "评论感知支持操作便利。",
        ),
        _pattern(
            "M09C_M10C_M11C",
            M12DEvidenceDomain.SEMANTIC_SCENE,
            ["user_task", "target_group", "battlefield"],
            ["smart_control", "remote_control", "BF_OPERATION_CONVENIENCE"],
            ["智能", "远程", "操作", "省心"],
            "语义画像指向智能控制或操作省心场景。",
        ),
        _pattern(
            "M12C",
            M12DEvidenceDomain.CLAIM_VALUE,
            ["claim_value_roles", "positive_claims_json", "claim_value_summary_json"],
            ["sales_driver_estimated", "smart_control"],
            ["sales_driver_estimated", "智能控制"],
            "M12C 显示智能控制卖点具备销量转化证据。",
        ),
    ]


def _ac_self_clean_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M03B",
            M12DEvidenceDomain.PARAM_FACT,
            ["param_values_json"],
            ["self_clean", "mildew_proof", "anti_mildew", "filter_clean"],
            ["自清洁", "防霉", "清洁"],
            "参数事实显示自清洁或防霉维护能力。",
        ),
        _pattern(
            "M04C",
            M12DEvidenceDomain.FACT_CLAIM,
            ["fact_claim_codes", "claim_codes", "dimension_profile_json"],
            ["durability_quality", "health_clean_air"],
            ["自清洁", "防霉", "清洁"],
            "事实卖点指向维护省心，但单一厂家表达需封顶。",
            weak_expression_only=True,
        ),
        _pattern(
            "M05C",
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            ["dimension_summary_json", "signal_summary_json", "evidence_examples_json"],
            ["self_clean", "maintenance", "odor"],
            ["自清洁", "清洁", "防霉", "异味", "维护"],
            "评论感知支持维护省心。",
        ),
        _pattern(
            "M09C_M10C_M11C",
            M12DEvidenceDomain.SEMANTIC_SCENE,
            ["user_task", "target_group", "battlefield"],
            ["maintenance", "operation_maintenance", "BF_OPERATION_MAINTENANCE"],
            ["维护", "省心", "清洁"],
            "语义画像指向维护省心场景。",
        ),
    ]


def _ac_budget_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M04C",
            M12DEvidenceDomain.CLAIM_POSITION,
            ["claim_codes", "unsupported_claim_codes", "dimension_position_profile_json", "dimension_profile_json"],
            ["price_value"],
            ["性价比", "价格", "低价", "补贴", "划算"],
            "价格价值表达或位置标签只能作为弱表达候选。",
            weak_expression_only=True,
        ),
        _pattern(
            "M05C",
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            ["dimension_summary_json", "signal_summary_json", "evidence_examples_json"],
            ["price_value", "value_for_money", "budget"],
            ["性价比", "划算", "便宜", "价格", "预算", "值"],
            "评论感知支持预算内配置获得感。",
        ),
        _pattern(
            "M07",
            M12DEvidenceDomain.MARKET_ACCEPTANCE,
            ["price_band_category", "price_band_size", "same_pool_price_percentile", "same_pool_volume_percentile", "sales_volume_total"],
            ["low", "mid_low"],
            ["low", "mid_low", "销量"],
            "市场价格位置和销量支持预算配置效率。",
        ),
        _pattern(
            "M12C",
            M12DEvidenceDomain.CLAIM_VALUE,
            ["claim_value_roles", "positive_claims_json", "claim_value_summary_json"],
            ["sales_driver_estimated", "price_value"],
            ["sales_driver_estimated", "性价比", "预算"],
            "M12C 显示价格价值卖点具备销量转化证据。",
        ),
    ]


def _ac_seasonal_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        *_ac_capacity_patterns(),
        *_ac_dehumid_patterns(),
        _pattern(
            "M09C_M10C_M11C",
            M12DEvidenceDomain.SEMANTIC_SCENE,
            ["user_task", "target_group", "battlefield"],
            ["seasonal_reliability", "extreme_weather", "BF_SEASONAL_RELIABILITY"],
            ["夏天", "冬天", "梅雨", "潮湿", "低温", "高温"],
            "语义画像指向季节或极端天气可靠性。",
        ),
    ]


def _ac_dehumid_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M03B",
            M12DEvidenceDomain.PARAM_FACT,
            ["param_values_json"],
            ["dehumidification", "humidity_control"],
            ["除湿", "湿度"],
            "参数事实显示除湿或湿度控制能力。",
        ),
        _pattern(
            "M04C",
            M12DEvidenceDomain.FACT_CLAIM,
            ["fact_claim_codes", "claim_codes", "dimension_profile_json"],
            ["humidity_control", "temperature_performance"],
            ["除湿", "干爽", "潮湿"],
            "事实卖点指向除湿，但单一厂家表达需封顶。",
            weak_expression_only=True,
        ),
        _pattern(
            "M05C",
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            ["dimension_summary_json", "signal_summary_json", "evidence_examples_json"],
            ["dehumidification", "humidity"],
            ["除湿", "潮湿", "梅雨", "干爽", "湿"],
            "评论感知支持潮湿环境除湿安心。",
        ),
        _pattern(
            "M09C_M10C_M11C",
            M12DEvidenceDomain.SEMANTIC_SCENE,
            ["user_task", "target_group", "battlefield"],
            ["dehumidification", "seasonal_reliability", "humidity"],
            ["除湿", "潮湿", "梅雨"],
            "语义画像指向潮湿或季节除湿场景。",
        ),
    ]


def _ac_mid_high_market_pattern() -> M12DAnchorEvidencePattern:
    return _pattern(
        "M07",
        M12DEvidenceDomain.MARKET_ACCEPTANCE,
        ["price_band_category", "price_band_size", "same_pool_volume_percentile", "sales_volume_total"],
        ["mid_high", "high"],
        ["mid_high", "high", "高价"],
        "市场价格位置显示中高/高价格段。",
    )


def _ac_low_market_pattern() -> M12DAnchorEvidencePattern:
    return _pattern(
        "M07",
        M12DEvidenceDomain.MARKET_ACCEPTANCE,
        ["price_band_category", "price_band_size", "same_pool_volume_percentile", "sales_volume_total"],
        ["low", "mid_low"],
        ["low", "mid_low", "低价", "销量"],
        "市场价格位置显示低/中低价格段。",
    )


def _picture_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M03B",
            M12DEvidenceDomain.PARAM_FACT,
            ["core_picture_params_json"],
            ["mini_led_flag", "mini_led_type", "display_tech_class", "local_dimming_zone_count", "declared_brightness_nit_or_band"],
            ["MiniLED", "OLED", "QLED", "亮度", "分区", "画质", "HDR", "色域", "4K"],
            "参数事实显示画质升级能力。",
        ),
        _pattern(
            "M04C",
            M12DEvidenceDomain.FACT_CLAIM,
            ["fact_claim_codes", "dimension_profile_json", "claim_summary_json"],
            ["tv_claim_miniled", "tv_claim_oled", "tv_claim_qled", "tv_claim_hdr", "tv_claim_picture_chip"],
            ["MiniLED", "高端画质", "画质", "控光", "分区"],
            "事实卖点指向画质升级。",
        ),
        _pattern(
            "M05C",
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            ["dimension_summary_json", "claim_comment_support_json", "evidence_examples_json"],
            ["picture_screen_experience", "tv_claim_miniled"],
            ["画质", "清晰", "亮度", "电影", "观影"],
            "评论感知支持画质体验。",
        ),
        _pattern(
            "M09C_M10C_M11C",
            M12DEvidenceDomain.SEMANTIC_SCENE,
            ["user_task", "target_group", "battlefield"],
            ["TASK_PREMIUM_PICTURE_EXPERIENCE", "TG_PREMIUM_AV_ENTHUSIAST", "BF_PREMIUM_PICTURE_UPGRADE"],
            ["高端画质", "影音", "画质"],
            "语义画像指向高端画质战场或影音任务。",
        ),
        _pattern(
            "M12C",
            M12DEvidenceDomain.CLAIM_VALUE,
            ["claim_codes", "claim_value_roles", "positive_claims_json"],
            ["tv_claim_miniled", "tv_claim_oled", "tv_claim_qled", "tv_claim_picture_chip", "premium"],
            ["premium", "高溢价", "正向贡献"],
            "M12C 显示画质卖点具备支付价值。",
        ),
    ]


def _dynamic_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M03B",
            M12DEvidenceDomain.PARAM_FACT,
            ["core_gaming_params_json"],
            ["refresh_rate_hz", "hdmi_2_1_flag", "vrr_flag", "low_latency_flag", "memc_flag"],
            ["144", "120Hz", "144Hz", "刷新率", "VRR", "HDMI2.1", "低延迟"],
            "参数事实显示动态流畅能力。",
        ),
        _pattern(
            "M04C",
            M12DEvidenceDomain.FACT_CLAIM,
            ["fact_claim_codes", "dimension_profile_json"],
            ["tv_claim_high_refresh", "tv_claim_hdmi_2_1", "tv_claim_vrr", "tv_claim_low_latency"],
            ["高刷", "游戏", "刷新率", "HDMI2.1"],
            "事实卖点指向游戏或运动流畅。",
        ),
        _pattern(
            "M05C",
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            ["dimension_summary_json", "signal_summary_json", "evidence_examples_json"],
            ["motion_gaming", "sports_gaming"],
            ["游戏", "体育", "高刷", "流畅"],
            "评论感知支持游戏或运动流畅。",
        ),
        _pattern(
            "M09C_M10C_M11C",
            M12DEvidenceDomain.SEMANTIC_SCENE,
            ["user_task", "battlefield"],
            ["TASK_GAMING_SPORTS_SMOOTHNESS", "BF_GAMING_SPORTS_FLUENCY"],
            ["游戏", "体育", "流畅"],
            "语义画像指向游戏/体育流畅场景。",
        ),
    ]


def _immersion_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M03B",
            M12DEvidenceDomain.PARAM_FACT,
            ["core_picture_params_json"],
            ["screen_size_inch", "audio_power_w", "dolby_vision_flag", "dolby_atmos_flag"],
            ["大屏", "杜比", "音响", "沉浸"],
            "参数事实显示大屏或观影沉浸能力。",
        ),
        _pattern(
            "M05C",
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            ["signal_summary_json", "evidence_examples_json", "supported_param_codes"],
            ["cinema_immersion", "living_room_viewing", "screen_size_inch"],
            ["客厅", "电影", "追剧", "观影", "沉浸"],
            "评论感知支持客厅观影或影院沉浸。",
        ),
        _pattern(
            "M09C_M10C_M11C",
            M12DEvidenceDomain.SEMANTIC_SCENE,
            ["user_task", "target_group", "battlefield"],
            ["TASK_LARGE_SCREEN_UPGRADE", "TASK_CINEMA_IMMERSION", "TG_MAINSTREAM_FAMILY_VIEWER", "BF_MAINSTREAM_LIVING_BALANCE"],
            ["客厅", "大屏", "影院", "追剧", "观影", "沉浸"],
            "语义画像指向客厅观影或大屏升级场景。",
        ),
    ]


def _budget_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M04C",
            M12DEvidenceDomain.CLAIM_POSITION,
            ["claim_codes", "unsupported_claim_codes", "dimension_position_profile_json"],
            ["tv_claim_value_price", "tv_claim_price_value", "value_price", "price_value"],
            ["性价比", "价格实惠", "预算", "划算"],
            "价格价值表达或位置标签只能作为弱表达候选。",
            weak_expression_only=True,
        ),
        _pattern(
            "M05C",
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            ["dimension_summary_json", "signal_summary_json", "evidence_examples_json"],
            ["value_for_money", "budget_value"],
            ["性价比", "划算", "这个价格", "预算"],
            "评论感知支持预算内配置获得感。",
        ),
        _pattern(
            "M07",
            M12DEvidenceDomain.MARKET_ACCEPTANCE,
            ["price_band_category", "price_band_size", "volume_percentile_in_size", "sales_volume_total"],
            ["low", "mid_low"],
            ["mid_low", "低价", "销量"],
            "同尺寸价格和销量位置支持预算价值。",
        ),
        _pattern(
            "M12C",
            M12DEvidenceDomain.CLAIM_VALUE,
            ["claim_value_roles", "positive_claims_json", "opportunity_claims_json"],
            ["customer_gain", "value_for_money", "high_price_intercept"],
            ["客户获得价值", "价格拦截", "预算"],
            "M12C 显示配置获得感或价格拦截价值。",
        ),
    ]


def _comfort_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M03B",
            M12DEvidenceDomain.PARAM_FACT,
            ["core_eye_care_params_json"],
            ["low_blue_light_flag", "flicker_free_flag", "anti_glare_flag", "eye_care_mode"],
            ["低蓝光", "无频闪", "护眼", "抗反光"],
            "参数事实显示护眼长看能力。",
        ),
        _pattern(
            "M05C",
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            ["dimension_summary_json", "evidence_examples_json"],
            ["eye_care", "long_watch"],
            ["护眼", "孩子", "老人", "久看"],
            "评论感知支持护眼长看。",
        ),
    ]


def _operation_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M03B",
            M12DEvidenceDomain.PARAM_FACT,
            ["core_system_params_json"],
            ["ai_chip_flag", "voice_control_flag", "wifi_flag", "cast_flag", "iot_flag", "smart_system"],
            ["AI", "语音", "投屏", "IoT", "智能", "互联"],
            "参数事实显示智能互联能力。",
        ),
        _pattern(
            "M04C",
            M12DEvidenceDomain.FACT_CLAIM,
            ["fact_claim_codes", "dimension_profile_json"],
            ["tv_claim_smart_iot", "tv_claim_voice_control", "tv_claim_screen_casting"],
            ["智能", "语音", "投屏", "互联"],
            "事实卖点指向智能互联。",
        ),
        _pattern(
            "M09C_M10C_M11C",
            M12DEvidenceDomain.SEMANTIC_SCENE,
            ["user_task", "battlefield"],
            ["TASK_SMART_CASTING_IOT", "BF_SMART_CONNECTED_EXPERIENCE"],
            ["智能", "互联", "投屏"],
            "语义画像指向智能互联任务或战场。",
        ),
    ]


def _aesthetic_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M03B",
            M12DEvidenceDomain.PARAM_FACT,
            ["param_values_json"],
            ["slim_body_flag", "wall_mount_fit", "bezel_less_flag", "art_frame_flag"],
            ["超薄", "贴墙", "全面屏", "壁画"],
            "参数事实显示家装融合能力。",
        ),
        _pattern(
            "M04C",
            M12DEvidenceDomain.FACT_CLAIM,
            ["fact_claim_codes", "dimension_profile_json"],
            ["tv_claim_slim_body", "tv_claim_art_frame", "tv_claim_wall_mount"],
            ["超薄", "贴墙", "壁画", "外观"],
            "事实卖点指向家装融合。",
        ),
        _pattern(
            "M09C_M10C_M11C",
            M12DEvidenceDomain.SEMANTIC_SCENE,
            ["user_task", "target_group", "battlefield"],
            ["TASK_NEW_HOME_DECOR_INTEGRATION", "TG_NEW_HOME_DECOR_USER", "BF_HOME_DECOR_INTEGRATION"],
            ["新家", "家装", "外观"],
            "语义画像指向家装融合场景。",
        ),
    ]


def _core_experience_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M03B",
            M12DEvidenceDomain.PARAM_FACT,
            ["core_picture_params_json", "core_gaming_params_json", "core_system_params_json"],
            ["screen_size_inch", "mini_led_flag", "refresh_rate_hz", "ai_chip_flag"],
            ["尺寸", "画质", "刷新率", "AI"],
            "参数事实显示核心体验配置。",
        )
    ]


def _av_semantic_patterns() -> list[M12DAnchorEvidencePattern]:
    return [
        _pattern(
            "M09C_M10C_M11C",
            M12DEvidenceDomain.SEMANTIC_SCENE,
            ["user_task", "target_group", "battlefield"],
            ["TASK_PREMIUM_PICTURE_EXPERIENCE", "TASK_CINEMA_IMMERSION", "TG_PREMIUM_AV_ENTHUSIAST"],
            ["影音", "观影", "电影", "画质"],
            "语义画像指向影音用户或观影任务。",
        )
    ]


def _mid_high_market_pattern() -> M12DAnchorEvidencePattern:
    return _pattern(
        "M07",
        M12DEvidenceDomain.MARKET_ACCEPTANCE,
        ["price_band_category", "price_band_size", "price_percentile_in_size", "volume_percentile_in_size"],
        ["mid_high", "high"],
        ["mid_high", "high"],
        "市场价格位置显示中高/高价格段。",
    )


def _low_market_pattern() -> M12DAnchorEvidencePattern:
    return _pattern(
        "M07",
        M12DEvidenceDomain.MARKET_ACCEPTANCE,
        ["price_band_category", "price_band_size", "volume_percentile_in_size"],
        ["low", "mid_low"],
        ["low", "mid_low"],
        "市场价格位置显示低/中低价格段。",
    )


def _size_market_pattern() -> M12DAnchorEvidencePattern:
    return _pattern(
        "M07",
        M12DEvidenceDomain.MARKET_ACCEPTANCE,
        ["screen_size_inch", "size_segment", "screen_size_class", "price_band_size", "volume_percentile_in_size"],
        ["large_60_69", "xlarge_70_85", "ultra_large"],
        ["65", "75", "85", "大屏"],
        "市场尺寸池和销量位置提供同尺寸参照。",
    )


def _value_theme(
    code: str,
    name_cn: str,
    family_code: str,
    family_cn: str,
    definition_cn: str,
    rank: int,
    patterns: list[M12DAnchorEvidencePattern],
) -> M12DStandardValueThemeDefinition:
    return M12DStandardValueThemeDefinition(
        value_theme_code=code,
        value_theme_cn=name_cn,
        value_theme_family_code=family_code,
        value_theme_family_cn=family_cn,
        definition_cn=definition_cn,
        candidate_rank=rank,
        evidence_patterns=patterns,
    )


def _purchase_reason(
    code: str,
    name_cn: str,
    family_code: str,
    family_cn: str,
    related_value_theme_codes: list[str],
    definition_cn: str,
    required_logic_cn: str,
    weak_boundary_cn: str,
    decision_question_cn: str,
    rank: int,
    patterns: list[M12DAnchorEvidencePattern],
    gate_domain_groups: list[list[M12DEvidenceDomain]],
) -> M12DStandardPurchaseReasonDefinition:
    return M12DStandardPurchaseReasonDefinition(
        purchase_reason_code=code,
        purchase_reason_cn=name_cn,
        purchase_reason_family_code=family_code,
        purchase_reason_family_cn=family_cn,
        related_value_theme_codes=related_value_theme_codes,
        definition_cn=definition_cn,
        required_logic_cn=required_logic_cn,
        weak_boundary_cn=weak_boundary_cn,
        decision_question_cn=decision_question_cn,
        candidate_rank=rank,
        evidence_patterns=patterns,
        candidate_gate_domain_groups=gate_domain_groups,
    )


def _pattern(
    module_code: str,
    domain: M12DEvidenceDomain,
    summary_keys: list[str],
    exact_codes: list[str],
    terms: list[str],
    support_label_cn: str,
    *,
    weak_expression_only: bool = False,
) -> M12DAnchorEvidencePattern:
    return M12DAnchorEvidencePattern(
        module_code=module_code,
        evidence_domain=domain,
        summary_keys=summary_keys,
        exact_codes=exact_codes,
        terms=terms,
        support_label_cn=support_label_cn,
        weak_expression_only=weak_expression_only,
    )
