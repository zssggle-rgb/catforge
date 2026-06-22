"""Ability registry for CatForge analyst CLI.

The registry is intentionally deterministic. It lets agent-facing skills know
which commands exist, what each command expects, and whether it is an atomic
ability or a SOP orchestration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


AbilityType = Literal["atom", "sop", "router"]


@dataclass(frozen=True)
class AbilityDefinition:
    code: str
    ability_type: AbilityType
    description_cn: str
    required_inputs: tuple[str, ...] = ()
    optional_inputs: tuple[str, ...] = ()
    source_modules: tuple[str, ...] = ()
    status: str = "planned"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


ATOM_ABILITIES: tuple[AbilityDefinition, ...] = (
    AbilityDefinition(
        code="resolve-sku",
        ability_type="atom",
        description_cn="把品牌、型号、SKU code 或自然语言 query 解析到唯一 SKU 或候选 SKU。",
        required_inputs=(),
        optional_inputs=("query", "sku_code", "model_name", "product_category", "batch_id"),
        source_modules=("M03B", "M04C", "M05C", "M07", "M11D"),
        status="implemented",
    ),
    AbilityDefinition(
        code="sku-fact-brief",
        ability_type="atom",
        description_cn="汇总单 SKU 的参数、卖点、评论、市场、用户任务、目标客群、价值战场和销量分配。",
        required_inputs=("sku_code|query",),
        source_modules=("M03B", "M04C", "M05C", "M07", "M09C", "M10C", "M11C", "M11D"),
    ),
    AbilityDefinition(
        code="same-size-price-candidates",
        ability_type="atom",
        description_cn="按同尺寸、同价格带和邻近价格带找可比 SKU 候选。",
        required_inputs=("sku_code|query",),
        optional_inputs=("price_band_expand", "candidate_limit"),
        source_modules=("M03B", "M07", "M11D"),
    ),
    AbilityDefinition(
        code="semantic-overlap",
        ability_type="atom",
        description_cn="计算 SKU 之间的用户任务、目标客群和价值战场重合。",
        required_inputs=("sku_code", "candidate_sku_code"),
        source_modules=("M09C", "M10C", "M11C", "M11D"),
    ),
    AbilityDefinition(
        code="sales-overlap",
        ability_type="atom",
        description_cn="计算两个 SKU 在重叠在售周内的周均销量、周均销额、价格和平台结构差异。",
        required_inputs=("sku_code", "candidate_sku_code"),
        source_modules=("M01", "M07"),
    ),
    AbilityDefinition(
        code="param-claim-overlap",
        ability_type="atom",
        description_cn="计算两个 SKU 的参数、卖点、卖点位置和参数档位的重合与差异。",
        required_inputs=("sku_code", "candidate_sku_code"),
        source_modules=("M03B", "M04C"),
    ),
    AbilityDefinition(
        code="comment-support",
        ability_type="atom",
        description_cn="查询评论对卖点、参数、用户任务、目标客群和价值战场的正负向支撑。",
        required_inputs=("sku_code|query",),
        optional_inputs=("claim_code", "param_code", "user_task_code", "target_group_code", "battlefield_code"),
        source_modules=("M05C",),
    ),
    AbilityDefinition(
        code="semantic-dimension-space",
        ability_type="atom",
        description_cn="查询某个用户任务、目标客群或价值战场的市场空间、SKU 贡献和分布。",
        required_inputs=("dimension_type", "dimension_code|query"),
        optional_inputs=("brand_name", "size_tier", "price_band", "sku_limit"),
        source_modules=("M11D",),
    ),
    AbilityDefinition(
        code="opportunity-gaps",
        ability_type="atom",
        description_cn="查询某 SKU 的机会战场、用户观察战场、拖后腿战场和价格/参数/卖点/评论卡点。",
        required_inputs=("sku_code|query",),
        source_modules=("M03B", "M04C", "M05C", "M07", "M11C", "M11D"),
    ),
)


SOP_ABILITIES: tuple[AbilityDefinition, ...] = (
    AbilityDefinition(
        code="competitor-set",
        ability_type="sop",
        description_cn="按同尺寸价格、同价值战场、同任务/客群、同参数/卖点、销量验证生成竞品集合。",
        required_inputs=("sku_code|query",),
        source_modules=("M03B", "M04C", "M05C", "M07", "M09C", "M10C", "M11C", "M11D"),
    ),
    AbilityDefinition(
        code="why-sales-diff",
        ability_type="sop",
        description_cn="解释两个 SKU 为什么卖得好或卖得差，必须使用重叠在售周周均销量/销额。",
        required_inputs=("sku_code", "candidate_sku_code"),
        source_modules=("M01", "M03B", "M04C", "M05C", "M07", "M09C", "M10C", "M11C", "M11D"),
    ),
    AbilityDefinition(
        code="premium-claim-drivers",
        ability_type="sop",
        description_cn="识别用户选择卖点、销量支撑卖点、溢价卖点、基础卖点和拖后腿卖点。",
        required_inputs=("sku_code|query",),
        source_modules=("M03B", "M04C", "M05C", "M07", "M09C", "M10C", "M11C", "M11D"),
    ),
    AbilityDefinition(
        code="battlefield-space",
        ability_type="sop",
        description_cn="查询价值战场市场空间、SKU 贡献、品牌分布和尺寸价格分布。",
        required_inputs=("dimension_code|query",),
        source_modules=("M11D",),
    ),
    AbilityDefinition(
        code="battlefield-opportunity",
        ability_type="sop",
        description_cn="分析某 SKU 能否通过价格、参数、卖点调整进入或强化更多价值战场。",
        required_inputs=("sku_code|query",),
        source_modules=("M03B", "M04C", "M05C", "M07", "M11C", "M11D"),
    ),
    AbilityDefinition(
        code="sku-business-brief",
        ability_type="sop",
        description_cn="生成单 SKU 面向业务用户的综合画像和市场位置摘要。",
        required_inputs=("sku_code|query",),
        source_modules=("M03B", "M04C", "M05C", "M07", "M09C", "M10C", "M11C", "M11D"),
    ),
)


ROUTER_ABILITIES: tuple[AbilityDefinition, ...] = (
    AbilityDefinition(
        code="ask",
        ability_type="router",
        description_cn="把自然语言问题路由到 SOP 或原子能力，不承担核心计算。",
        required_inputs=("question",),
        optional_inputs=("product_category", "batch_id"),
        status="implemented",
    ),
)


ALL_ABILITIES: tuple[AbilityDefinition, ...] = (*ATOM_ABILITIES, *SOP_ABILITIES, *ROUTER_ABILITIES)
ABILITIES_BY_CODE: dict[str, AbilityDefinition] = {ability.code: ability for ability in ALL_ABILITIES}


def list_abilities(*, ability_type: AbilityType | None = None) -> list[dict[str, object]]:
    abilities = ALL_ABILITIES if ability_type is None else tuple(item for item in ALL_ABILITIES if item.ability_type == ability_type)
    return [ability.to_dict() for ability in abilities]


def get_ability(code: str) -> AbilityDefinition | None:
    return ABILITIES_BY_CODE.get(code)
