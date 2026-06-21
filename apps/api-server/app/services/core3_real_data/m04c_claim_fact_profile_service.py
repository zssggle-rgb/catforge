"""M04C SKU claim fact profiles and claim-position coverage.

M04C is deterministic. It consumes cleaned/evidence selling-point text and the
current M03B SKU parameter profile. It does not read comments and it does not
decide premium value; comment verification and value-battlefield judgement stay
in later layers.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import entities
from app.schemas.core3_real_data import Core3ModuleRunResultSchema
from app.services.core3_real_data.cleaning_repositories import SourceBatchReader
from app.services.core3_real_data.constants import (
    CORE3_M03B_RULE_VERSION,
    CORE3_M04C_MODULE_VERSION,
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M04C_TV_TAXONOMY_VERSION,
    Core3EvidenceStatus,
    Core3EvidenceType,
    Core3ModuleCode,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.param_extraction_repositories import (
    ParamRepositoryHashConflictError,
    ParamRepositoryWriteResult,
)
from app.services.core3_real_data.repositories import Core3BaseRepository, Core3RepositoryContext
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.runner import Core3ModuleTarget


M04C_PROFILE_ID_HASH_VERSION = "m04c-claim-profile-id-v1"
M04C_PROFILE_HASH_VERSION = "m04c-claim-profile-v1"
M04C_FACT_ID_HASH_VERSION = "m04c-claim-fact-id-v1"
M04C_FACT_HASH_VERSION = "m04c-claim-fact-v1"
M04C_POSITION_ID_HASH_VERSION = "m04c-claim-position-id-v1"
M04C_POSITION_HASH_VERSION = "m04c-claim-position-v1"
M04C_COVERAGE_ID_HASH_VERSION = "m04c-claim-coverage-id-v1"
M04C_COVERAGE_HASH_VERSION = "m04c-claim-coverage-v1"

SUPPORT_SUPPORTED = "supported"
SUPPORT_PARTIAL = "partially_supported"
SUPPORT_UNSUPPORTED = "unsupported_by_param"
SUPPORT_UNKNOWN = "param_unknown"
SUPPORT_NOT_APPLICABLE = "not_param_applicable"

POSITION_CLAIMED = "claimed"
POSITION_SUPPORTED = "supported"
INPUT_SOURCE_AUTO = "auto"
INPUT_SOURCE_EVIDENCE = "evidence"
INPUT_SOURCE_CLEAN = "clean"
INPUT_SOURCE_RAW = "raw"


@dataclass(frozen=True)
class M04CClaimDefinition:
    claim_code: str
    claim_name: str
    dimension_code: str
    subtype_code: str
    claim_kind: str
    patterns: tuple[str, ...]
    support_param_codes: tuple[str, ...] = ()
    support_keywords: tuple[str, ...] = ()
    negative_patterns: tuple[str, ...] = ()
    support_required: bool = True
    service_separate: bool = False


@dataclass(frozen=True)
class M04CPositionDefinition:
    dimension_code: str
    position_code: str
    position_name: str
    position_rank: int | None
    rule_summary: str


@dataclass(frozen=True)
class M04CClaimTaxonomy:
    taxonomy_version: str
    product_category: str
    product_category_label_cn: str
    raw_category_label_cn: str
    sku_code_prefix: str
    claims: tuple[M04CClaimDefinition, ...]
    positions: tuple[M04CPositionDefinition, ...]

    @property
    def claims_by_code(self) -> dict[str, M04CClaimDefinition]:
        return {claim.claim_code: claim for claim in self.claims}

    @property
    def positions_by_key(self) -> dict[tuple[str, str], M04CPositionDefinition]:
        return {(position.dimension_code, position.position_code): position for position in self.positions}


@dataclass(frozen=True)
class M04CClaimRecord:
    sku_code: str
    model_name: str | None
    brand_name: str | None
    claim_text: str
    claim_seq: int | None = None
    source_claim_key: str | None = None
    evidence_id: str | None = None
    raw_claim_text: str | None = None


@dataclass(frozen=True)
class M04CWritePayload:
    payload: dict[str, Any]

    def to_record_payload(self) -> dict[str, Any]:
        return self.payload


@dataclass(frozen=True)
class M04CServiceResult:
    input_count: int
    source_used: str
    sku_profile_count: int
    claim_fact_count: int
    dimension_position_count: int
    position_coverage_count: int
    fact_claim_count: int
    service_separate_claim_count: int
    unmatched_claim_text_count: int
    param_unknown_claim_count: int
    unsupported_claim_count: int
    warnings: list[str]
    write_summary: dict[str, dict[str, int]]
    summary: dict[str, Any]

    @property
    def created_output_count(self) -> int:
        return sum(item["created_count"] for item in self.write_summary.values())


def tv_claim_taxonomy_v0_1() -> M04CClaimTaxonomy:
    claims = (
        _claim(
            "tv_claim_miniled_display",
            "MiniLED 显示/背光",
            "picture_quality",
            "display_tech",
            ("mini\\s*led", "miniled", "mini-led", "百级分区", "千级分区"),
            support_param_codes=("mini_led_flag", "mini_led_type", "display_tech_class", "backlight_subtype"),
            support_keywords=("miniled", "mini led", "mini-led"),
            negative_patterns=("非\\s*mini\\s*led", "非miniled"),
        ),
        _claim(
            "tv_claim_qd_miniled_display",
            "QD-MiniLED/量子点增强",
            "picture_quality",
            "display_tech",
            ("qd\\s*mini", "量子点", "qled"),
            support_param_codes=("mini_led_type", "quantum_dot_flag", "display_tech_class"),
            support_keywords=("qd-miniled", "qd miniled", "量子点", "qled"),
        ),
        _claim(
            "tv_claim_rgb_miniled_display",
            "RGB-MiniLED 显示",
            "picture_quality",
            "display_tech",
            ("rgb\\s*mini", "rgb-miniled", "rgb miniled"),
            support_param_codes=("mini_led_type", "rgb_structure_flag", "display_tech_class"),
            support_keywords=("rgb-miniled", "rgb miniled"),
        ),
        _claim(
            "tv_claim_oled_self_lit",
            "OLED 自发光",
            "picture_quality",
            "display_tech",
            ("oled自发光", "自发光oled", "oled电视", "oled屏"),
            support_param_codes=("display_technology_family", "display_tech_class"),
            support_keywords=("oled", "自发光"),
            negative_patterns=("媲美oled", "比.*oled", "类似oled", "不是oled", "非oled"),
        ),
        _claim(
            "tv_claim_hdr_high_brightness",
            "HDR/高亮画质",
            "picture_quality",
            "brightness_hdr",
            ("\\bhdr\\b", "xdr", "杜比视界", "高亮", "峰值亮度", "尼特", "nits?"),
            support_param_codes=("hdr_support_flag", "declared_brightness_nit_or_band"),
            support_keywords=("hdr", "xdr", "亮度", "nit", "尼特", "dolby vision", "杜比视界"),
        ),
        _claim(
            "tv_claim_wide_color_accuracy",
            "广色域/色彩还原",
            "picture_quality",
            "color",
            ("色域", "色准", "delta", "Δe", "原彩", "真彩", "量子点色彩"),
            support_param_codes=("color_gamut_ratio", "high_color_gamut_flag", "quantum_dot_flag"),
            support_keywords=("色域", "色准", "delta", "Δe", "高色域", "量子点"),
        ),
        _claim(
            "tv_claim_local_dimming",
            "分区控光",
            "picture_quality",
            "dimming",
            ("分区", "控光", "背光分区", "local\\s*dimming"),
            support_param_codes=("local_dimming_zone_count",),
            support_keywords=("分区", "控光", "zones"),
        ),
        _claim(
            "tv_claim_picture_engine_ai",
            "画质芯片/AI 画质引擎",
            "picture_quality",
            "picture_engine",
            ("画质芯片", "画质引擎", "ai画质", "图像处理", "ai调校"),
            support_param_codes=("processor_chip_model", "ai_capability_flag", "ai_model_capability_flag"),
            support_keywords=("画质", "ai", "芯片"),
        ),
        _claim(
            "tv_claim_eye_care_display",
            "护眼显示",
            "picture_quality",
            "eye_care",
            ("护眼", "低蓝光", "无频闪", "莱茵"),
            support_param_codes=("hdr_support_flag", "declared_brightness_nit_or_band", "declared_refresh_rate_hz"),
            support_keywords=("护眼", "低蓝光", "莱茵", "无频闪"),
        ),
        _claim(
            "tv_claim_high_refresh_rate",
            "高刷新率",
            "motion_gaming",
            "refresh",
            ("刷新率", "高刷", "\\d{3}\\s*hz", "120hz", "144hz", "240hz", "288hz"),
            support_param_codes=("declared_refresh_rate_hz",),
            support_keywords=("120", "144", "240", "刷新", "hz"),
        ),
        _claim(
            "tv_claim_gaming_low_latency",
            "游戏/低延迟",
            "motion_gaming",
            "gaming",
            ("游戏", "电竞", "低延迟", "allm", "vrr", "g-sync", "freesync"),
            support_param_codes=("declared_refresh_rate_hz", "hdmi_version_mix", "hdmi_2_1_port_count"),
            support_keywords=("game", "游戏", "电竞", "allm", "vrr", "hdmi2.1"),
        ),
        _claim(
            "tv_claim_hdmi21_connectivity",
            "HDMI2.1 连接",
            "motion_gaming",
            "gaming_connectivity",
            ("hdmi\\s*2\\.1", "满血hdmi", "4k\\s*120"),
            support_param_codes=("hdmi_version_mix", "hdmi_2_1_port_count"),
            support_keywords=("hdmi2.1", "2.1", "4k120"),
        ),
        _claim(
            "tv_claim_ai_large_model",
            "AI 大模型/智能能力",
            "smart_interaction",
            "ai",
            ("ai大模型", "大模型", "ai智能", "ai能力", "人工智能"),
            support_param_codes=("ai_model_name", "ai_model_capability_flag", "ai_capability_flag"),
            support_keywords=("ai", "大模型", "人工智能"),
        ),
        _claim(
            "tv_claim_voice_control",
            "语音控制",
            "smart_interaction",
            "voice",
            ("语音", "远场", "声控", "免遥控"),
            support_param_codes=("voice_engine", "voice_recognition_flag", "far_field_voice_flag"),
            support_keywords=("语音", "远场", "voice"),
        ),
        _claim(
            "tv_claim_smart_home_iot",
            "家电联动/全屋智能",
            "smart_interaction",
            "iot",
            ("智家", "智能家居", "家电联动", "全屋智能", "物联", "hilink"),
            support_param_codes=("whole_home_control_flag", "smart_tv_flag", "network_tv_flag"),
            support_keywords=("全屋", "联动", "智能家居", "hilink"),
        ),
        _claim(
            "tv_claim_casting_connectivity",
            "投屏/无线连接",
            "smart_interaction",
            "connectivity",
            ("投屏", "wifi", "wi-fi", "蓝牙", "nfc"),
            support_param_codes=("wifi_builtin_flag", "network_tv_flag", "smart_tv_flag"),
            support_keywords=("wifi", "投屏", "蓝牙", "nfc"),
        ),
        _claim(
            "tv_claim_camera_interaction",
            "摄像头互动",
            "smart_interaction",
            "camera",
            ("摄像头", "视频通话", "体感"),
            support_param_codes=("camera_flag",),
            support_keywords=("摄像头", "camera"),
        ),
        _claim(
            "tv_claim_dolby_audio_video",
            "杜比/影音认证",
            "audio_cinema",
            "certification",
            ("杜比", "dolby", "dts", "hdr10"),
            support_param_codes=("hdr_support_flag",),
            support_keywords=("dolby", "杜比", "dts", "hdr10"),
        ),
        _claim(
            "tv_claim_speaker_sound",
            "音响/声道能力",
            "audio_cinema",
            "speaker",
            ("音响", "音效", "声道", "低音", "扬声器", "功率"),
            support_param_codes=(),
            support_keywords=("音响", "音效", "声道", "speaker"),
        ),
        _claim(
            "tv_claim_theater_scene",
            "影院/观影场景",
            "audio_cinema",
            "theater",
            ("影院", "imax", "电影", "观影"),
            support_param_codes=("screen_size_inch", "hdr_support_flag", "declared_brightness_nit_or_band"),
            support_keywords=("影院", "imax", "电影", "观影"),
        ),
        _claim(
            "tv_claim_slim_body",
            "超薄机身",
            "appearance_installation",
            "thin",
            ("超薄", "薄至", "纤薄", "\\d+(?:\\.\\d+)?\\s*mm"),
            support_param_codes=("slim_design_label", "slim_design_flag", "body_thickness_mm"),
            support_keywords=("超薄", "纤薄", "薄", "mm"),
        ),
        _claim(
            "tv_claim_full_screen_design",
            "全面屏/窄边框",
            "appearance_installation",
            "full_screen",
            ("全面屏", "超窄边", "窄边框", "屏占比"),
            support_param_codes=("full_screen_design_flag",),
            support_keywords=("全面屏", "窄边"),
        ),
        _claim(
            "tv_claim_flush_wall_mount",
            "无缝贴墙/壁画安装",
            "appearance_installation",
            "wall_mount",
            ("贴墙", "无缝贴墙", "壁画", "零距"),
            support_param_codes=("flush_wall_mount_flag",),
            support_keywords=("贴墙", "壁画", "零距"),
        ),
        _claim(
            "tv_claim_premium_material_design",
            "金属/质感设计",
            "appearance_installation",
            "material_design",
            ("金属", "一体成型", "质感"),
            support_param_codes=("product_color",),
            support_keywords=("金属", "质感"),
        ),
        _claim(
            "tv_claim_chip_performance",
            "芯片/处理器性能",
            "system_performance",
            "chip",
            ("芯片", "四核", "cpu", "处理器", "主频"),
            support_param_codes=("processor_chip_model", "processor_vendor", "cpu_core_count", "cpu_frequency_ghz"),
            support_keywords=("芯片", "cpu", "处理器", "core", "ghz"),
        ),
        _claim(
            "tv_claim_memory_storage",
            "运行内存/存储",
            "system_performance",
            "memory_storage",
            ("运行内存", "\\b内存\\b", "ram", "rom", "存储"),
            support_param_codes=("ram_gb", "storage_gb"),
            support_keywords=("ram", "rom", "内存", "存储", "gb"),
        ),
        _claim(
            "tv_claim_energy_efficiency",
            "能效/节能",
            "energy_value",
            "energy",
            ("一级能效", "能效", "节能"),
            support_param_codes=("energy_efficiency_grade", "energy_efficiency_index", "standby_power_w"),
            support_keywords=("能效", "节能", "一级"),
        ),
        _claim(
            "tv_claim_value_price",
            "价格/性价比表达",
            "energy_value",
            "price_value",
            ("性价比", "同价位", "入门", "划算", "补贴"),
            support_required=False,
            claim_kind="market_position",
        ),
        _claim(
            "tv_claim_service_fulfillment",
            "服务履约/售后",
            "service_fulfillment",
            "service",
            ("安装", "送货", "售后", "保修", "质保", "客服", "服务"),
            support_required=False,
            service_separate=True,
            claim_kind="service_fulfillment",
        ),
    )
    positions = (
        _position("picture_quality", "picture_flagship_miniled_composite", "MiniLED 复合画质旗舰型", 50, "MiniLED/QD/RGB/OLED 且至少 4 类画质卖点同时出现"),
        _position("picture_quality", "picture_advanced_display", "高阶显示技术型", 40, "具备 MiniLED/QD/RGB/OLED 或至少 3 类画质卖点"),
        _position("picture_quality", "picture_enhanced_quality", "画质增强型", 30, "具备 HDR/高亮/高色域/高刷/画质引擎等增强卖点"),
        _position("picture_quality", "picture_basic_mentioned", "基础画质提及型", 10, "有画质卖点但缺少更强组合支撑"),
        _position("motion_gaming", "gaming_competitive", "电竞游戏强化型", 40, "高刷 + 游戏低延迟/HDMI2.1 同时出现"),
        _position("motion_gaming", "gaming_ready", "游戏准备型", 20, "有高刷、游戏或 HDMI2.1 任一卖点"),
        _position("smart_interaction", "smart_ai_iot", "AI 全屋互联型", 40, "AI/语音与家电联动或摄像头互动同时出现"),
        _position("smart_interaction", "smart_ai_voice", "AI 语音增强型", 30, "AI 和语音同时出现"),
        _position("smart_interaction", "smart_basic", "基础智能连接型", 10, "有智能、语音、投屏、WiFi 或摄像头任一卖点"),
        _position("audio_cinema", "cinema_theater", "家庭影院型", 30, "影院场景与影音/音响卖点同时出现"),
        _position("audio_cinema", "audio_enhanced", "影音增强型", 20, "有杜比、音响、影院任一卖点"),
        _position("appearance_installation", "gallery_wall_mount", "壁画贴墙型", 40, "无缝贴墙或壁画安装卖点出现"),
        _position("appearance_installation", "slim_full_screen", "轻薄全面屏型", 30, "超薄、全面屏或金属质感外观卖点出现"),
        _position("system_performance", "performance_strong", "芯片存储强化型", 30, "芯片/处理器与内存/存储同时出现"),
        _position("system_performance", "performance_mentioned", "基础性能提及型", 10, "有芯片或内存存储任一卖点"),
        _position("energy_value", "energy_value_efficient", "能效价值型", 20, "有能效或节能卖点"),
        _position("energy_value", "price_value_mentioned", "价格价值表达型", 10, "有性价比、补贴、同价位等表达"),
    )
    return M04CClaimTaxonomy(
        taxonomy_version=CORE3_M04C_TV_TAXONOMY_VERSION,
        product_category="TV",
        product_category_label_cn="彩电",
        raw_category_label_cn="彩电",
        sku_code_prefix="TV",
        claims=claims,
        positions=positions,
    )


class M04CTaxonomyLoader:
    def load(self, taxonomy_version: str, *, product_category: str = "TV") -> M04CClaimTaxonomy:
        normalized = str(product_category or "TV").upper()
        if normalized == "TV" and taxonomy_version == CORE3_M04C_TV_TAXONOMY_VERSION:
            return tv_claim_taxonomy_v0_1()
        raise ValueError(f"{product_category} 标准卖点 taxonomy 未发布，不能生成 M04C 卖点事实画像。")


class M04CClaimEvidenceReader(Core3BaseRepository):
    def list_promo_evidence(
        self,
        batch_id: str,
        *,
        sku_code_prefix: str | None = "TV",
        target_sku_codes: Sequence[str] = (),
    ) -> list[M04CClaimRecord]:
        rows = self._list_promo_evidence_rows(
            batch_id,
            evidence_types=(Core3EvidenceType.PROMO_SENTENCE.value,),
            sku_code_prefix=sku_code_prefix,
            target_sku_codes=target_sku_codes,
        )
        if not rows:
            rows = self._list_promo_evidence_rows(
                batch_id,
                evidence_types=(Core3EvidenceType.PROMO_RAW.value,),
                sku_code_prefix=sku_code_prefix,
                target_sku_codes=target_sku_codes,
            )
        records = [_record_from_evidence(row) for row in rows if _present_text(row.clean_value or row.text_value or row.raw_value)]
        return _dedupe_claim_records(records)

    def _list_promo_evidence_rows(
        self,
        batch_id: str,
        *,
        evidence_types: Sequence[str],
        sku_code_prefix: str | None,
        target_sku_codes: Sequence[str],
    ) -> list[entities.Core3EvidenceAtom]:
        stmt = (
            select(entities.Core3EvidenceAtom)
            .where(entities.Core3EvidenceAtom.project_id == self.project_id)
            .where(entities.Core3EvidenceAtom.category_code == self.category_code.value)
            .where(entities.Core3EvidenceAtom.batch_id == batch_id)
            .where(entities.Core3EvidenceAtom.is_current.is_(True))
            .where(entities.Core3EvidenceAtom.evidence_status == Core3EvidenceStatus.CURRENT.value)
            .where(entities.Core3EvidenceAtom.evidence_type.in_(tuple(evidence_types)))
            .order_by(
                entities.Core3EvidenceAtom.sku_code,
                entities.Core3EvidenceAtom.evidence_type,
                entities.Core3EvidenceAtom.evidence_field,
                entities.Core3EvidenceAtom.evidence_id,
            )
            .limit(200000)
        )
        if sku_code_prefix:
            stmt = stmt.where(entities.Core3EvidenceAtom.sku_code.like(f"{sku_code_prefix}%"))
        if target_sku_codes:
            stmt = stmt.where(entities.Core3EvidenceAtom.sku_code.in_(tuple(target_sku_codes)))
        return list(self.db.execute(stmt).scalars())

    def list_clean_claims(
        self,
        batch_id: str,
        *,
        sku_code_prefix: str | None = "TV",
        target_sku_codes: Sequence[str] = (),
    ) -> list[M04CClaimRecord]:
        stmt = (
            select(entities.Core3CleanClaim)
            .where(entities.Core3CleanClaim.project_id == self.project_id)
            .where(entities.Core3CleanClaim.category_code == self.category_code.value)
            .where(entities.Core3CleanClaim.batch_id == batch_id)
            .where(entities.Core3CleanClaim.record_status == "active")
            .where(entities.Core3CleanClaim.claim_text_presence == "present")
            .order_by(
                entities.Core3CleanClaim.sku_code,
                entities.Core3CleanClaim.claim_seq,
                entities.Core3CleanClaim.clean_claim_id,
            )
            .limit(200000)
        )
        if sku_code_prefix:
            stmt = stmt.where(entities.Core3CleanClaim.sku_code.like(f"{sku_code_prefix}%"))
        if target_sku_codes:
            stmt = stmt.where(entities.Core3CleanClaim.sku_code.in_(tuple(target_sku_codes)))
        rows = list(self.db.execute(stmt).scalars())
        return _dedupe_claim_records([_record_from_clean_claim(row) for row in rows if _present_text(row.clean_claim_text)])

    def list_raw_selling_points(
        self,
        *,
        raw_category_label_cn: str,
        sku_code_prefix: str | None = "TV",
        target_sku_codes: Sequence[str] = (),
    ) -> list[M04CClaimRecord]:
        sql = """
            select
                id::text as source_pk,
                model_code::text as sku_code,
                model::text as model_name,
                brand::text as brand_name,
                variable::text as claim_seq_raw,
                selling_point::text as claim_text
            from selling_points_data
            where selling_point is not null
              and btrim(selling_point::text) <> ''
              and category = :raw_category
        """
        params: dict[str, Any] = {"raw_category": raw_category_label_cn}
        if sku_code_prefix:
            sql += " and model_code::text like :sku_like"
            params["sku_like"] = f"{sku_code_prefix}%"
        if target_sku_codes:
            sql += " and model_code::text = any(:sku_codes)"
            params["sku_codes"] = list(target_sku_codes)
        sql += " order by model_code, variable, id limit 200000"
        rows = self.db.execute(text(sql), params).mappings()
        return [
            M04CClaimRecord(
                sku_code=str(row["sku_code"] or ""),
                model_name=_none_if_blank(row["model_name"]),
                brand_name=_none_if_blank(row["brand_name"]),
                claim_text=str(row["claim_text"] or ""),
                raw_claim_text=str(row["claim_text"] or ""),
                claim_seq=_parse_claim_seq(row["claim_seq_raw"]),
                source_claim_key=f"raw:{row['source_pk']}",
            )
            for row in rows
            if _present_text(row["sku_code"]) and _present_text(row["claim_text"])
        ]


class M04CClaimProfileRepository(Core3BaseRepository):
    def save_profiles(self, profiles: Sequence[Any], *, replace_on_hash_conflict: bool = False) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuClaimFactProfile,
            profiles,
            unique_fields=("batch_id", "taxonomy_version", "sku_code", "rule_version", "is_current"),
            hash_field="profile_hash",
            replace_existing=replace_on_hash_conflict,
        )

    def save_facts(self, facts: Sequence[Any], *, replace_on_hash_conflict: bool = False) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuClaimFact,
            facts,
            unique_fields=("batch_id", "taxonomy_version", "sku_code", "source_claim_key", "claim_code", "rule_version", "is_current"),
            hash_field="fact_hash",
            replace_existing=replace_on_hash_conflict,
        )

    def save_positions(self, positions: Sequence[Any], *, replace_on_hash_conflict: bool = False) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuClaimDimensionPosition,
            positions,
            unique_fields=("batch_id", "taxonomy_version", "sku_code", "dimension_code", "position_source", "rule_version", "is_current"),
            hash_field="position_hash",
            replace_existing=replace_on_hash_conflict,
        )

    def save_coverages(self, coverages: Sequence[Any], *, replace_on_hash_conflict: bool = False) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3ClaimPositionCoverage,
            coverages,
            unique_fields=("batch_id", "taxonomy_version", "dimension_code", "position_code", "position_source", "rule_version", "is_current"),
            hash_field="coverage_hash",
            replace_existing=replace_on_hash_conflict,
        )

    def _save_many(
        self,
        model_cls: Any,
        payloads: Sequence[Any],
        *,
        unique_fields: tuple[str, ...],
        hash_field: str | None,
        replace_existing: bool,
    ) -> ParamRepositoryWriteResult:
        records: list[Any] = []
        created_count = 0
        reused_count = 0
        for payload in payloads:
            record, created = self._save_one(
                model_cls,
                payload,
                unique_fields=unique_fields,
                hash_field=hash_field,
                replace_existing=replace_existing,
            )
            records.append(record)
            created_count += 1 if created else 0
            reused_count += 0 if created else 1
        return ParamRepositoryWriteResult(records=tuple(records), created_count=created_count, reused_count=reused_count)

    def _save_one(
        self,
        model_cls: Any,
        payload: Any,
        *,
        unique_fields: tuple[str, ...],
        hash_field: str | None,
        replace_existing: bool,
    ) -> tuple[Any, bool]:
        normalized_payload = _normalize_payload(model_cls, payload, project_id=self.project_id, category_code=self.category_code.value)
        existing = self._find_by_unique(model_cls, normalized_payload, unique_fields)
        if existing is not None:
            if replace_existing:
                _update_existing(existing, normalized_payload)
                self.db.flush()
                return existing, False
            _assert_same_hash(existing, normalized_payload, hash_field=hash_field, unique_fields=unique_fields, model_name=model_cls.__tablename__)
            return existing, False
        record = model_cls(**_jsonable(normalized_payload))
        self.db.add(record)
        self.db.flush()
        return record, True

    def _find_by_unique(self, model_cls: Any, payload: Mapping[str, Any], unique_fields: tuple[str, ...]) -> Any | None:
        stmt = select(model_cls).where(model_cls.project_id == self.project_id).where(model_cls.category_code == self.category_code.value)
        for field_name in unique_fields:
            field_value = payload.get(field_name)
            if field_value is None:
                raise ValueError(f"{model_cls.__tablename__}.{field_name} is required for idempotent write")
            stmt = stmt.where(getattr(model_cls, field_name) == field_value)
        return self.db.execute(stmt).scalars().first()


class M04CRunner:
    module_code = Core3ModuleCode.M04C

    def __init__(self, db: Session) -> None:
        self.db = db

    def run(self, context: Core3RunContext, target: Core3ModuleTarget) -> Core3ModuleRunResultSchema:
        batch_id = str(target.metadata.get("batch_id") or context.batch_id or "")
        if not batch_id:
            return _blocked_result(
                project_id=context.project_id,
                category_code=context.category_code.value,
                batch_id=None,
                run_id=context.run_id,
                message_cn="M04C 缺少 M00 batch_id，无法生成 SKU 卖点事实画像。",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            )
        return self.run_batch(
            project_id=context.project_id,
            category_code=context.category_code.value,
            batch_id=batch_id,
            run_id=context.run_id,
            module_run_id=target.metadata.get("module_run_id"),
            product_category=str(target.metadata.get("product_category") or "TV"),
            taxonomy_version=str(target.metadata.get("taxonomy_version") or CORE3_M04C_TV_TAXONOMY_VERSION),
            rule_version=str(target.metadata.get("rule_version") or CORE3_M04C_TV_RULE_VERSION),
            input_source=str(target.metadata.get("input_source") or INPUT_SOURCE_AUTO),
            target_sku_codes=target.target_ids,
            force_rebuild=bool(target.metadata.get("force_rebuild")),
        )

    def run_batch(
        self,
        *,
        project_id: str,
        batch_id: str,
        category_code: str = "TV",
        run_id: str | None = None,
        module_run_id: str | None = None,
        product_category: str = "TV",
        taxonomy_version: str = CORE3_M04C_TV_TAXONOMY_VERSION,
        rule_version: str = CORE3_M04C_TV_RULE_VERSION,
        input_source: str = INPUT_SOURCE_AUTO,
        target_sku_codes: Sequence[str] = (),
        force_rebuild: bool = False,
    ) -> Core3ModuleRunResultSchema:
        started_at = datetime.now(timezone.utc)
        repository_context = Core3RepositoryContext(db=self.db, project_id=project_id, category_code=category_code)
        try:
            SourceBatchReader(repository_context).get_consumable_batch(batch_id)
        except ValueError as exc:
            return _blocked_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                message_cn=str(exc),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )
        try:
            with self.db.begin_nested():
                service_result = M04CService(repository_context).build_batch(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    product_category=product_category,
                    taxonomy_version=taxonomy_version,
                    rule_version=rule_version,
                    input_source=input_source,
                    target_sku_codes=target_sku_codes,
                    force_rebuild=force_rebuild,
                )
        except ParamRepositoryHashConflictError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m04c_claim_hash_conflict",
                message_cn="M04C 卖点事实画像结果与既有同批次业务键结果 hash 不一致，已停止以避免覆盖旧结果。",
                error_message=str(exc),
            )
        except ValueError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m04c_claim_profile_failed",
                message_cn="M04C 卖点事实画像生成失败，请检查卖点输入、M03B 参数画像或 taxonomy 配置。",
                error_message=str(exc),
            )

        summary_json = {
            "batch_id": batch_id,
            "module_version": CORE3_M04C_MODULE_VERSION,
            "taxonomy_version": taxonomy_version,
            "rule_version": rule_version,
            "product_category": product_category,
            "target_sku_codes": list(target_sku_codes),
            **service_result.summary,
        }
        status = Core3RunStatus.WARNING if service_result.warnings else Core3RunStatus.SUCCESS
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M04C,
            status=status,
            input_count=service_result.input_count,
            changed_input_count=service_result.created_output_count,
            output_count=service_result.sku_profile_count + service_result.claim_fact_count + service_result.dimension_position_count + service_result.position_coverage_count,
            output_hash=stable_hash(summary_json, version="m04c_claim_profile_summary_v1"),
            warnings=service_result.warnings,
            review_issues=[],
            downstream_impacts=[
                {"module_code": "M08", "reason": "SKU 卖点事实画像变化会影响后续事实画像和价值战场判断。"},
                {"module_code": "M12", "reason": "卖点位置覆盖变化会影响竞品池召回。"},
            ],
            summary_json=summary_json,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )


class M04CService:
    def __init__(self, context: Core3RepositoryContext) -> None:
        self.context = context

    def build_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        product_category: str = "TV",
        taxonomy_version: str = CORE3_M04C_TV_TAXONOMY_VERSION,
        rule_version: str = CORE3_M04C_TV_RULE_VERSION,
        input_source: str = INPUT_SOURCE_AUTO,
        target_sku_codes: Sequence[str] = (),
        force_rebuild: bool = False,
    ) -> M04CServiceResult:
        taxonomy = M04CTaxonomyLoader().load(taxonomy_version, product_category=product_category)
        records, source_used = self._read_claim_records(
            batch_id,
            taxonomy=taxonomy,
            input_source=input_source,
            target_sku_codes=target_sku_codes,
        )
        param_profiles = self._read_param_profiles(batch_id, sku_codes=sorted({record.sku_code for record in records}))
        profiles, facts, positions, coverages, summary = M04CProfileBuilder(
            project_id=self.context.project_id,
            category_code=self.context.category_code.value,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            taxonomy=taxonomy,
            rule_version=rule_version,
            input_source=source_used,
        ).build(records, param_profiles)
        repository = M04CClaimProfileRepository(self.context)
        write_results = {
            "sku_claim_profiles": repository.save_profiles(profiles, replace_on_hash_conflict=force_rebuild),
            "claim_facts": repository.save_facts(facts, replace_on_hash_conflict=force_rebuild),
            "dimension_positions": repository.save_positions(positions, replace_on_hash_conflict=force_rebuild),
            "position_coverages": repository.save_coverages(coverages, replace_on_hash_conflict=force_rebuild),
        }
        write_summary = {name: _write_summary(result) for name, result in write_results.items()}
        warnings = _warnings(summary)
        return M04CServiceResult(
            input_count=len(records),
            source_used=source_used,
            sku_profile_count=len(profiles),
            claim_fact_count=len(facts),
            dimension_position_count=len(positions),
            position_coverage_count=len(coverages),
            fact_claim_count=int(summary["fact_claim_count"]),
            service_separate_claim_count=int(summary["service_separate_claim_count"]),
            unmatched_claim_text_count=int(summary["unmatched_claim_text_count"]),
            param_unknown_claim_count=int(summary["param_unknown_claim_count"]),
            unsupported_claim_count=int(summary["unsupported_claim_count"]),
            warnings=warnings,
            write_summary=write_summary,
            summary={**summary, "source_used": source_used, "write_summary": write_summary},
        )

    def _read_claim_records(
        self,
        batch_id: str,
        *,
        taxonomy: M04CClaimTaxonomy,
        input_source: str,
        target_sku_codes: Sequence[str],
    ) -> tuple[list[M04CClaimRecord], str]:
        reader = M04CClaimEvidenceReader(self.context)
        normalized = _normalize_input_source(input_source)
        if normalized in {INPUT_SOURCE_AUTO, INPUT_SOURCE_EVIDENCE}:
            records = reader.list_promo_evidence(batch_id, sku_code_prefix=taxonomy.sku_code_prefix, target_sku_codes=target_sku_codes)
            if records or normalized == INPUT_SOURCE_EVIDENCE:
                return records, INPUT_SOURCE_EVIDENCE
        if normalized in {INPUT_SOURCE_AUTO, INPUT_SOURCE_CLEAN}:
            records = reader.list_clean_claims(batch_id, sku_code_prefix=taxonomy.sku_code_prefix, target_sku_codes=target_sku_codes)
            if records or normalized == INPUT_SOURCE_CLEAN:
                return records, INPUT_SOURCE_CLEAN
        records = reader.list_raw_selling_points(
            raw_category_label_cn=taxonomy.raw_category_label_cn,
            sku_code_prefix=taxonomy.sku_code_prefix,
            target_sku_codes=target_sku_codes,
        )
        return records, INPUT_SOURCE_RAW

    def _read_param_profiles(self, batch_id: str, *, sku_codes: Sequence[str]) -> dict[str, entities.Core3SkuParamProfile]:
        if not sku_codes:
            return {}
        stmt = (
            select(entities.Core3SkuParamProfile)
            .where(entities.Core3SkuParamProfile.project_id == self.context.project_id)
            .where(entities.Core3SkuParamProfile.category_code == self.context.category_code.value)
            .where(entities.Core3SkuParamProfile.batch_id == batch_id)
            .where(entities.Core3SkuParamProfile.rule_version == CORE3_M03B_RULE_VERSION)
            .where(entities.Core3SkuParamProfile.sku_code.in_(tuple(sku_codes)))
            .order_by(entities.Core3SkuParamProfile.updated_at.desc(), entities.Core3SkuParamProfile.created_at.desc())
        )
        result: dict[str, entities.Core3SkuParamProfile] = {}
        for profile in self.context.db.execute(stmt).scalars():
            result.setdefault(profile.sku_code, profile)
        return result


class M04CProfileBuilder:
    def __init__(
        self,
        *,
        project_id: str,
        category_code: str,
        batch_id: str,
        taxonomy: M04CClaimTaxonomy,
        run_id: str | None = None,
        module_run_id: str | None = None,
        rule_version: str = CORE3_M04C_TV_RULE_VERSION,
        input_source: str = INPUT_SOURCE_EVIDENCE,
    ) -> None:
        self.project_id = project_id
        self.category_code = category_code
        self.batch_id = batch_id
        self.run_id = run_id
        self.module_run_id = module_run_id
        self.taxonomy = taxonomy
        self.rule_version = rule_version
        self.input_source = input_source
        self.positions_by_key = taxonomy.positions_by_key

    def build(
        self,
        records: Iterable[M04CClaimRecord],
        param_profiles: Mapping[str, entities.Core3SkuParamProfile],
    ) -> tuple[list[M04CWritePayload], list[M04CWritePayload], list[M04CWritePayload], list[M04CWritePayload], dict[str, Any]]:
        clean_records = [record for record in records if _sku_allowed(record.sku_code, self.taxonomy.sku_code_prefix) and _present_text(record.claim_text)]
        records_by_sku: dict[str, list[M04CClaimRecord]] = defaultdict(list)
        for record in clean_records:
            records_by_sku[record.sku_code].append(record)
        profiles: list[M04CWritePayload] = []
        facts: list[M04CWritePayload] = []
        positions: list[M04CWritePayload] = []
        unmatched_count = 0
        support_status_counts: Counter[str] = Counter()
        service_separate_claim_count = 0

        for sku_code in sorted(records_by_sku):
            sku_result = self._build_sku(sku_code, records_by_sku[sku_code], param_profiles.get(sku_code))
            profiles.append(sku_result["profile"])
            facts.extend(sku_result["facts"])
            positions.extend(sku_result["positions"])
            unmatched_count += int(sku_result["unmatched_claim_text_count"])
            support_status_counts.update(sku_result["support_status_counts"])
            service_separate_claim_count += int(sku_result["service_separate_claim_count"])

        coverages = self._build_coverages(positions, total_sku_count=len(records_by_sku))
        dimension_distribution = _dimension_distribution(facts)
        summary = {
            "input_claim_text_count": len(clean_records),
            "sku_profile_count": len(profiles),
            "claim_fact_count": len(facts),
            "dimension_position_count": len(positions),
            "position_coverage_count": len(coverages),
            "fact_claim_count": support_status_counts[SUPPORT_SUPPORTED] + support_status_counts[SUPPORT_PARTIAL],
            "service_separate_claim_count": service_separate_claim_count,
            "unmatched_claim_text_count": unmatched_count,
            "param_unknown_claim_count": support_status_counts[SUPPORT_UNKNOWN],
            "unsupported_claim_count": support_status_counts[SUPPORT_UNSUPPORTED],
            "support_status_counts": dict(sorted(support_status_counts.items())),
            "dimension_distribution": dimension_distribution,
            "category_boundary_filter": f"sku_code_prefix_{self.taxonomy.sku_code_prefix}",
            "taxonomy_hash": stable_hash(_taxonomy_summary(self.taxonomy), version="m04c_claim_taxonomy_asset_hash_v1"),
        }
        return profiles, facts, positions, coverages, summary

    def _build_sku(
        self,
        sku_code: str,
        records: list[M04CClaimRecord],
        param_profile: entities.Core3SkuParamProfile | None,
    ) -> dict[str, Any]:
        model_name = _first_present(record.model_name for record in records)
        brand_name = _first_present(record.brand_name for record in records)
        facts: list[M04CWritePayload] = []
        unmatched_claim_text_count = 0
        support_status_counts: Counter[str] = Counter()
        service_separate_claim_count = 0
        profile_texts = []
        for index, record in enumerate(records, start=1):
            source_claim_key = record.source_claim_key or _source_claim_key(sku_code, record.claim_seq, record.claim_text, index)
            matches = self._match_claims(record.claim_text)
            if not matches:
                unmatched_claim_text_count += 1
                continue
            profile_texts.append(
                {
                    "source_claim_key": source_claim_key,
                    "claim_seq": record.claim_seq,
                    "claim_text": record.claim_text,
                    "matched_claim_codes": [claim.claim_code for claim in matches],
                }
            )
            for claim in matches:
                support = _param_support(claim, param_profile)
                support_status_counts[support["status"]] += 1
                if claim.service_separate:
                    service_separate_claim_count += 1
                fact_flag = support["status"] in {SUPPORT_SUPPORTED, SUPPORT_PARTIAL} and not claim.service_separate
                facts.append(
                    M04CWritePayload(
                        self._fact_payload(
                            sku_code=sku_code,
                            model_name=record.model_name or model_name,
                            brand_name=record.brand_name or brand_name,
                            source_claim_key=source_claim_key,
                            claim_seq=record.claim_seq,
                            raw_claim_text=record.raw_claim_text or record.claim_text,
                            clean_claim_text=record.claim_text,
                            evidence_id=record.evidence_id,
                            claim=claim,
                            support=support,
                            fact_claim_flag=fact_flag,
                        )
                    )
                )

        positions = self._build_positions(sku_code, model_name, facts)
        profile = M04CWritePayload(
            self._profile_payload(
                sku_code=sku_code,
                model_name=model_name,
                brand_name=brand_name,
                raw_claim_count=len(records),
                profile_texts=profile_texts,
                facts=facts,
                positions=positions,
                unmatched_claim_text_count=unmatched_claim_text_count,
                service_separate_claim_count=service_separate_claim_count,
                support_status_counts=support_status_counts,
                param_profile=param_profile,
            )
        )
        return {
            "profile": profile,
            "facts": facts,
            "positions": positions,
            "unmatched_claim_text_count": unmatched_claim_text_count,
            "service_separate_claim_count": service_separate_claim_count,
            "support_status_counts": support_status_counts,
        }

    def _match_claims(self, text_value: str) -> list[M04CClaimDefinition]:
        matches = []
        normalized_text = _normalize_claim_text(text_value)
        for claim in self.taxonomy.claims:
            if any(re.search(pattern, normalized_text, flags=re.IGNORECASE) for pattern in claim.negative_patterns):
                continue
            if any(re.search(pattern, normalized_text, flags=re.IGNORECASE) for pattern in claim.patterns):
                matches.append(claim)
        return matches

    def _fact_payload(
        self,
        *,
        sku_code: str,
        model_name: str | None,
        brand_name: str | None,
        source_claim_key: str,
        claim_seq: int | None,
        raw_claim_text: str,
        clean_claim_text: str,
        evidence_id: str | None,
        claim: M04CClaimDefinition,
        support: dict[str, Any],
        fact_claim_flag: bool,
    ) -> dict[str, Any]:
        evidence_ids = [evidence_id] if evidence_id else []
        quality_flags = []
        if support["status"] == SUPPORT_UNKNOWN:
            quality_flags.append("param_profile_missing_or_unknown")
        elif support["status"] == SUPPORT_UNSUPPORTED:
            quality_flags.append("claim_not_supported_by_param_profile")
        if claim.service_separate:
            quality_flags.append("service_fulfillment_separate")
        payload = {
            "claim_fact_id": _claim_fact_id(self.project_id, self.batch_id, sku_code, source_claim_key, claim.claim_code, self.rule_version),
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "module_run_id": self.module_run_id,
            "product_category": self.taxonomy.product_category,
            "taxonomy_version": self.taxonomy.taxonomy_version,
            "sku_code": sku_code,
            "model_name": model_name,
            "brand_name": brand_name,
            "source_claim_key": source_claim_key,
            "claim_seq": claim_seq,
            "raw_claim_text": raw_claim_text,
            "clean_claim_text": clean_claim_text,
            "claim_code": claim.claim_code,
            "claim_name": claim.claim_name,
            "claim_dimension": claim.dimension_code,
            "claim_subtype": claim.subtype_code,
            "claim_kind": claim.claim_kind,
            "match_type": "taxonomy_keyword",
            "match_score": Decimal("1.0000"),
            "param_support_status": support["status"],
            "supporting_param_codes": support["supporting_param_codes"],
            "supporting_param_snapshot_json": support["snapshot"],
            "support_explanation": support["explanation"],
            "fact_claim_flag": fact_claim_flag,
            "service_separate_flag": claim.service_separate,
            "evidence_ids": evidence_ids,
            "quality_flags": quality_flags,
            "confidence": _claim_confidence(support["status"], claim),
            "is_current": True,
            "rule_version": self.rule_version,
        }
        payload["fact_hash"] = stable_hash(
            {
                "sku_code": sku_code,
                "source_claim_key": source_claim_key,
                "claim_code": claim.claim_code,
                "claim_text": clean_claim_text,
                "support": support,
                "fact_claim_flag": fact_claim_flag,
                "taxonomy_version": self.taxonomy.taxonomy_version,
                "rule_version": self.rule_version,
            },
            version=M04C_FACT_HASH_VERSION,
        )
        return payload

    def _build_positions(
        self,
        sku_code: str,
        model_name: str | None,
        facts: Sequence[M04CWritePayload],
    ) -> list[M04CWritePayload]:
        facts_by_dimension: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for fact in facts:
            payload = fact.payload
            if payload["service_separate_flag"]:
                continue
            facts_by_dimension[payload["claim_dimension"]].append(payload)
        positions = []
        for dimension_code in sorted(facts_by_dimension):
            dimension_facts = facts_by_dimension[dimension_code]
            claimed = {fact["claim_code"] for fact in dimension_facts}
            supported = {fact["claim_code"] for fact in dimension_facts if fact["fact_claim_flag"]}
            claimed_position = _position_for_dimension(dimension_code, claimed)
            supported_position = _position_for_dimension(dimension_code, supported)
            if claimed_position:
                positions.append(self._position_payload(sku_code, model_name, dimension_code, claimed_position, POSITION_CLAIMED, dimension_facts, claimed, supported))
            if supported_position:
                positions.append(self._position_payload(sku_code, model_name, dimension_code, supported_position, POSITION_SUPPORTED, dimension_facts, claimed, supported))
        return positions

    def _position_payload(
        self,
        sku_code: str,
        model_name: str | None,
        dimension_code: str,
        position_code: str,
        position_source: str,
        dimension_facts: Sequence[dict[str, Any]],
        claimed_codes: set[str],
        supported_codes: set[str],
    ) -> M04CWritePayload:
        definition = self.positions_by_key[(dimension_code, position_code)]
        source_codes = supported_codes if position_source == POSITION_SUPPORTED else claimed_codes
        basis_texts = [
            {
                "claim_code": fact["claim_code"],
                "claim_text": fact["clean_claim_text"],
                "param_support_status": fact["param_support_status"],
            }
            for fact in dimension_facts
            if fact["claim_code"] in source_codes
        ]
        evidence_ids = _unique_preserve_order(evidence_id for fact in dimension_facts for evidence_id in fact["evidence_ids"])
        payload = {
            "dimension_position_id": _dimension_position_id(self.project_id, self.batch_id, sku_code, self.taxonomy.taxonomy_version, dimension_code, position_source, self.rule_version),
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "module_run_id": self.module_run_id,
            "product_category": self.taxonomy.product_category,
            "taxonomy_version": self.taxonomy.taxonomy_version,
            "sku_code": sku_code,
            "model_name": model_name,
            "dimension_code": dimension_code,
            "position_code": position_code,
            "position_name": definition.position_name,
            "position_rank": definition.position_rank,
            "position_source": position_source,
            "basis_claim_codes": sorted(claimed_codes),
            "basis_fact_claim_codes": sorted(supported_codes),
            "basis_texts_json": basis_texts,
            "explanation": _position_explanation(definition, position_source, source_codes),
            "evidence_ids": evidence_ids,
            "quality_flags": [] if source_codes else ["empty_position_basis"],
            "confidence": Decimal("0.9000") if position_source == POSITION_SUPPORTED else Decimal("0.7600"),
            "is_current": True,
            "rule_version": self.rule_version,
        }
        payload["position_hash"] = stable_hash(
            {
                "sku_code": sku_code,
                "dimension_code": dimension_code,
                "position_code": position_code,
                "position_source": position_source,
                "basis_claim_codes": sorted(claimed_codes),
                "basis_fact_claim_codes": sorted(supported_codes),
                "taxonomy_version": self.taxonomy.taxonomy_version,
                "rule_version": self.rule_version,
            },
            version=M04C_POSITION_HASH_VERSION,
        )
        return M04CWritePayload(payload)

    def _profile_payload(
        self,
        *,
        sku_code: str,
        model_name: str | None,
        brand_name: str | None,
        raw_claim_count: int,
        profile_texts: list[dict[str, Any]],
        facts: Sequence[M04CWritePayload],
        positions: Sequence[M04CWritePayload],
        unmatched_claim_text_count: int,
        service_separate_claim_count: int,
        support_status_counts: Counter[str],
        param_profile: entities.Core3SkuParamProfile | None,
    ) -> dict[str, Any]:
        fact_payloads = [fact.payload for fact in facts]
        position_payloads = [position.payload for position in positions]
        claim_codes = sorted({fact["claim_code"] for fact in fact_payloads})
        fact_claim_codes = sorted({fact["claim_code"] for fact in fact_payloads if fact["fact_claim_flag"]})
        unsupported_claim_codes = sorted({fact["claim_code"] for fact in fact_payloads if fact["param_support_status"] == SUPPORT_UNSUPPORTED})
        service_claim_codes = sorted({fact["claim_code"] for fact in fact_payloads if fact["service_separate_flag"]})
        dimension_profile = _profile_dimension_summary(fact_payloads)
        position_profile = {
            f"{position['position_source']}:{position['dimension_code']}": {
                "position_code": position["position_code"],
                "position_name": position["position_name"],
                "basis_claim_codes": position["basis_claim_codes"],
                "basis_fact_claim_codes": position["basis_fact_claim_codes"],
            }
            for position in position_payloads
        }
        evidence_ids = _unique_preserve_order(evidence_id for fact in fact_payloads for evidence_id in fact["evidence_ids"])
        quality_flags = []
        if param_profile is None:
            quality_flags.append("m03b_param_profile_missing")
        if unmatched_claim_text_count:
            quality_flags.append("claim_text_unmatched")
        if support_status_counts[SUPPORT_UNSUPPORTED]:
            quality_flags.append("claim_param_support_conflict")
        claim_summary = {
            "taxonomy_version": self.taxonomy.taxonomy_version,
            "rule_version": self.rule_version,
            "input_source": self.input_source,
            "m03b_param_profile_hash": getattr(param_profile, "profile_hash", None),
            "raw_claim_count": raw_claim_count,
            "matched_claim_count": len(fact_payloads),
            "unmatched_claim_text_count": unmatched_claim_text_count,
            "support_status_counts": dict(sorted(support_status_counts.items())),
            "dimension_counts": {dimension: value["matched_claim_count"] for dimension, value in dimension_profile.items()},
        }
        payload = {
            "claim_profile_id": _claim_profile_id(self.project_id, self.batch_id, sku_code, self.taxonomy.taxonomy_version, self.rule_version),
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "module_run_id": self.module_run_id,
            "product_category": self.taxonomy.product_category,
            "taxonomy_version": self.taxonomy.taxonomy_version,
            "sku_code": sku_code,
            "model_name": model_name,
            "brand_name": brand_name,
            "raw_claim_count": raw_claim_count,
            "matched_claim_count": len(fact_payloads),
            "fact_claim_count": len(fact_claim_codes),
            "unsupported_claim_count": support_status_counts[SUPPORT_UNSUPPORTED],
            "param_unknown_claim_count": support_status_counts[SUPPORT_UNKNOWN],
            "service_separate_claim_count": service_separate_claim_count,
            "claim_texts_json": profile_texts,
            "claim_codes": claim_codes,
            "fact_claim_codes": fact_claim_codes,
            "unsupported_claim_codes": unsupported_claim_codes,
            "service_claim_codes": service_claim_codes,
            "dimension_profile_json": dimension_profile,
            "dimension_position_profile_json": position_profile,
            "claim_summary_json": claim_summary,
            "evidence_ids": evidence_ids,
            "quality_flags": quality_flags,
            "confidence": Decimal("0.8500") if param_profile is not None else Decimal("0.6500"),
            "is_current": True,
            "rule_version": self.rule_version,
        }
        payload["profile_hash"] = stable_hash(
            {
                "sku_code": sku_code,
                "claim_codes": claim_codes,
                "fact_claim_codes": fact_claim_codes,
                "dimension_profile": dimension_profile,
                "position_profile": position_profile,
                "claim_summary": claim_summary,
                "taxonomy_version": self.taxonomy.taxonomy_version,
                "rule_version": self.rule_version,
            },
            version=M04C_PROFILE_HASH_VERSION,
        )
        return payload

    def _build_coverages(self, positions: Sequence[M04CWritePayload], *, total_sku_count: int) -> list[M04CWritePayload]:
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for position in positions:
            payload = position.payload
            grouped[(payload["dimension_code"], payload["position_code"], payload["position_source"])].append(payload)
        coverages = []
        for key in sorted(grouped):
            dimension_code, position_code, position_source = key
            rows = grouped[key]
            definition = self.positions_by_key[(dimension_code, position_code)]
            sku_codes = sorted({row["sku_code"] for row in rows})
            basis_claim_codes = sorted({claim_code for row in rows for claim_code in row["basis_claim_codes"]})
            payload = {
                "position_coverage_id": _position_coverage_id(self.project_id, self.batch_id, self.taxonomy.taxonomy_version, dimension_code, position_code, position_source, self.rule_version),
                "project_id": self.project_id,
                "category_code": self.category_code,
                "batch_id": self.batch_id,
                "run_id": self.run_id,
                "module_run_id": self.module_run_id,
                "product_category": self.taxonomy.product_category,
                "taxonomy_version": self.taxonomy.taxonomy_version,
                "dimension_code": dimension_code,
                "position_code": position_code,
                "position_name": definition.position_name,
                "position_rank": definition.position_rank,
                "position_source": position_source,
                "rule_summary": definition.rule_summary,
                "sku_count": len(sku_codes),
                "sku_ratio": _ratio(len(sku_codes), total_sku_count),
                "sku_codes": sku_codes,
                "sample_sku_codes": sku_codes[:20],
                "basis_claim_codes": basis_claim_codes,
                "coverage_status": "covered" if sku_codes else "empty",
                "is_current": True,
                "rule_version": self.rule_version,
            }
            payload["coverage_hash"] = stable_hash(
                {
                    "dimension_code": dimension_code,
                    "position_code": position_code,
                    "position_source": position_source,
                    "sku_codes": sku_codes,
                    "taxonomy_version": self.taxonomy.taxonomy_version,
                    "rule_version": self.rule_version,
                },
                version=M04C_COVERAGE_HASH_VERSION,
            )
            coverages.append(M04CWritePayload(payload))
        return coverages


def _claim(
    claim_code: str,
    claim_name: str,
    dimension_code: str,
    subtype_code: str,
    patterns: Sequence[str],
    *,
    support_param_codes: Sequence[str] = (),
    support_keywords: Sequence[str] = (),
    negative_patterns: Sequence[str] = (),
    support_required: bool = True,
    service_separate: bool = False,
    claim_kind: str = "product_experience",
) -> M04CClaimDefinition:
    return M04CClaimDefinition(
        claim_code=claim_code,
        claim_name=claim_name,
        dimension_code=dimension_code,
        subtype_code=subtype_code,
        claim_kind=claim_kind,
        patterns=tuple(patterns),
        support_param_codes=tuple(support_param_codes),
        support_keywords=tuple(support_keywords),
        negative_patterns=tuple(negative_patterns),
        support_required=support_required,
        service_separate=service_separate,
    )


def _position(dimension_code: str, position_code: str, position_name: str, position_rank: int | None, rule_summary: str) -> M04CPositionDefinition:
    return M04CPositionDefinition(
        dimension_code=dimension_code,
        position_code=position_code,
        position_name=position_name,
        position_rank=position_rank,
        rule_summary=rule_summary,
    )


def _param_support(claim: M04CClaimDefinition, profile: entities.Core3SkuParamProfile | None) -> dict[str, Any]:
    if claim.service_separate:
        return {
            "status": SUPPORT_NOT_APPLICABLE,
            "supporting_param_codes": [],
            "snapshot": {},
            "explanation": "服务履约类卖点单独标记，不进入商品事实卖点。",
        }
    if not claim.support_required:
        return {
            "status": SUPPORT_NOT_APPLICABLE,
            "supporting_param_codes": [],
            "snapshot": {},
            "explanation": "该卖点属于价格/市场表达，M04C 不用参数判断其事实性。",
        }
    if profile is None:
        return {
            "status": SUPPORT_UNKNOWN,
            "supporting_param_codes": list(claim.support_param_codes),
            "snapshot": {},
            "explanation": "缺少该 SKU 的 M03B 参数画像，无法判断参数支撑。",
        }
    param_values = profile.param_values_json or {}
    snapshot: dict[str, Any] = {}
    supported_codes = []
    known_false_codes = []
    for code in claim.support_param_codes:
        entry = param_values.get(code)
        if isinstance(entry, Mapping):
            snapshot[code] = _compact_param_entry(entry)
            if _entry_supports_claim(code, entry, claim):
                supported_codes.append(code)
            elif _entry_is_known_false(entry):
                known_false_codes.append(code)
    if supported_codes:
        status = SUPPORT_SUPPORTED if len(supported_codes) == len(claim.support_param_codes) or len(supported_codes) >= 2 else SUPPORT_PARTIAL
        return {
            "status": status,
            "supporting_param_codes": supported_codes,
            "snapshot": snapshot,
            "explanation": f"参数画像中 {', '.join(supported_codes)} 与卖点匹配。",
        }
    profile_text = _normalize_claim_text(param_values)
    if claim.support_keywords and any(_normalize_claim_text(keyword) in profile_text for keyword in claim.support_keywords):
        return {
            "status": SUPPORT_PARTIAL,
            "supporting_param_codes": list(claim.support_param_codes),
            "snapshot": snapshot,
            "explanation": "参数画像文本中出现相关关键词，但未能定位到完整标准参数字段。",
        }
    if known_false_codes:
        return {
            "status": SUPPORT_UNSUPPORTED,
            "supporting_param_codes": known_false_codes,
            "snapshot": snapshot,
            "explanation": f"参数画像中 {', '.join(known_false_codes)} 明确为否或 0，与卖点不一致。",
        }
    return {
        "status": SUPPORT_UNKNOWN,
        "supporting_param_codes": list(claim.support_param_codes),
        "snapshot": snapshot,
        "explanation": "参数画像缺少可判断该卖点的标准参数或参数值未知。",
    }


def _entry_supports_claim(param_code: str, entry: Mapping[str, Any], claim: M04CClaimDefinition) -> bool:
    value_presence = str(entry.get("value_presence") or "").lower()
    if value_presence in {"unknown", "missing"}:
        return False
    if _entry_is_known_false(entry):
        return False
    value_text = _normalize_claim_text(
        " ".join(
            str(item)
            for item in (
                entry.get("normalized_value"),
                entry.get("value_text"),
                entry.get("numeric_value"),
                entry.get("raw_param_value"),
            )
            if item is not None
        )
    )
    if claim.support_keywords and any(_normalize_claim_text(keyword) in value_text for keyword in claim.support_keywords):
        return True
    normalized_value = entry.get("normalized_value")
    numeric_value = entry.get("numeric_value", normalized_value)
    if param_code == "declared_refresh_rate_hz" and claim.claim_code in {"tv_claim_high_refresh_rate", "tv_claim_gaming_low_latency"}:
        numeric = _to_decimal(numeric_value)
        return numeric is not None and numeric >= Decimal("120")
    if param_code == "declared_brightness_nit_or_band" and claim.claim_code == "tv_claim_hdr_high_brightness":
        numeric = _to_decimal(numeric_value)
        return numeric is None or numeric >= Decimal("500")
    if param_code == "local_dimming_zone_count":
        numeric = _to_decimal(numeric_value)
        return numeric is not None and numeric > Decimal("0")
    if isinstance(normalized_value, bool):
        return normalized_value
    if isinstance(normalized_value, (int, float, Decimal)):
        return Decimal(str(normalized_value)) > Decimal("0")
    return bool(str(normalized_value or entry.get("value_text") or "").strip())


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        match = re.search(r"-?\d+(?:\.\d+)?", str(value))
        return Decimal(match.group(0)) if match else None


def _entry_is_known_false(entry: Mapping[str, Any]) -> bool:
    normalized_value = entry.get("normalized_value")
    if normalized_value is False:
        return True
    if isinstance(normalized_value, bool):
        return False
    if isinstance(normalized_value, (int, float, Decimal)) and Decimal(str(normalized_value)) == Decimal("0"):
        return True
    value_text = _normalize_claim_text(" ".join(str(item) for item in (normalized_value, entry.get("value_text")) if item is not None))
    return value_text in {"false", "0", "否", "无", "不支持", "非miniled", "非mini led"}


def _compact_param_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    result = {}
    for key in ("normalized_value", "numeric_value", "value_text", "value_presence", "quality_flags"):
        if key in entry:
            result[key] = entry[key]
    return result


def _position_for_dimension(dimension_code: str, claim_codes: set[str]) -> str | None:
    if not claim_codes:
        return None
    if dimension_code == "picture_quality":
        display_codes = {"tv_claim_miniled_display", "tv_claim_qd_miniled_display", "tv_claim_rgb_miniled_display", "tv_claim_oled_self_lit"}
        if claim_codes & display_codes and len(claim_codes & {
            "tv_claim_miniled_display",
            "tv_claim_qd_miniled_display",
            "tv_claim_rgb_miniled_display",
            "tv_claim_oled_self_lit",
            "tv_claim_hdr_high_brightness",
            "tv_claim_wide_color_accuracy",
            "tv_claim_local_dimming",
            "tv_claim_picture_engine_ai",
            "tv_claim_eye_care_display",
            "tv_claim_high_refresh_rate",
        }) >= 4:
            return "picture_flagship_miniled_composite"
        if claim_codes & display_codes or len(claim_codes) >= 3:
            return "picture_advanced_display"
        if claim_codes & {
            "tv_claim_hdr_high_brightness",
            "tv_claim_wide_color_accuracy",
            "tv_claim_local_dimming",
            "tv_claim_picture_engine_ai",
            "tv_claim_eye_care_display",
            "tv_claim_high_refresh_rate",
        }:
            return "picture_enhanced_quality"
        return "picture_basic_mentioned"
    if dimension_code == "motion_gaming":
        if "tv_claim_high_refresh_rate" in claim_codes and claim_codes & {"tv_claim_gaming_low_latency", "tv_claim_hdmi21_connectivity"}:
            return "gaming_competitive"
        return "gaming_ready"
    if dimension_code == "smart_interaction":
        if claim_codes & {"tv_claim_ai_large_model", "tv_claim_voice_control"} and claim_codes & {"tv_claim_smart_home_iot", "tv_claim_camera_interaction"}:
            return "smart_ai_iot"
        if {"tv_claim_ai_large_model", "tv_claim_voice_control"}.issubset(claim_codes):
            return "smart_ai_voice"
        return "smart_basic"
    if dimension_code == "audio_cinema":
        if "tv_claim_theater_scene" in claim_codes and claim_codes & {"tv_claim_dolby_audio_video", "tv_claim_speaker_sound"}:
            return "cinema_theater"
        return "audio_enhanced"
    if dimension_code == "appearance_installation":
        if "tv_claim_flush_wall_mount" in claim_codes:
            return "gallery_wall_mount"
        return "slim_full_screen"
    if dimension_code == "system_performance":
        if {"tv_claim_chip_performance", "tv_claim_memory_storage"}.issubset(claim_codes):
            return "performance_strong"
        return "performance_mentioned"
    if dimension_code == "energy_value":
        if "tv_claim_energy_efficiency" in claim_codes:
            return "energy_value_efficient"
        if "tv_claim_value_price" in claim_codes:
            return "price_value_mentioned"
    return None


def _profile_dimension_summary(facts: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        grouped[fact["claim_dimension"]].append(fact)
    return {
        dimension_code: {
            "matched_claim_count": len(rows),
            "fact_claim_count": sum(1 for row in rows if row["fact_claim_flag"]),
            "service_separate_count": sum(1 for row in rows if row["service_separate_flag"]),
            "claim_codes": sorted({row["claim_code"] for row in rows}),
            "fact_claim_codes": sorted({row["claim_code"] for row in rows if row["fact_claim_flag"]}),
            "support_status_counts": dict(sorted(Counter(row["param_support_status"] for row in rows).items())),
        }
        for dimension_code, rows in sorted(grouped.items())
    }


def _dimension_distribution(facts: Sequence[M04CWritePayload]) -> dict[str, int]:
    counter = Counter(fact.payload["claim_dimension"] for fact in facts)
    return dict(sorted(counter.items()))


def _warnings(summary: Mapping[str, Any]) -> list[str]:
    warnings = []
    if int(summary.get("input_claim_text_count") or 0) == 0:
        warnings.append("m04c_empty_claim_input")
    if int(summary.get("sku_profile_count") or 0) == 0:
        warnings.append("m04c_empty_sku_profile_output")
    if int(summary.get("param_unknown_claim_count") or 0) > 0:
        warnings.append("m04c_param_support_unknown")
    if summary.get("source_used") == INPUT_SOURCE_RAW:
        warnings.append("m04c_raw_claim_fallback_used")
    return warnings


def _write_summary(result: ParamRepositoryWriteResult) -> dict[str, int]:
    return {
        "created_count": result.created_count,
        "reused_count": result.reused_count,
        "record_count": len(result.records),
    }


def _record_from_evidence(row: entities.Core3EvidenceAtom) -> M04CClaimRecord:
    claim_text = str(row.clean_value or row.text_value or row.raw_value or "")
    return M04CClaimRecord(
        sku_code=str(row.sku_code or ""),
        model_name=row.model_name,
        brand_name=row.brand_name,
        claim_text=claim_text,
        raw_claim_text=str(row.raw_value or claim_text),
        source_claim_key=f"evidence:{row.evidence_id}",
        evidence_id=row.evidence_id,
        claim_seq=row.sentence_seq,
    )


def _record_from_clean_claim(row: entities.Core3CleanClaim) -> M04CClaimRecord:
    return M04CClaimRecord(
        sku_code=str(row.sku_code or ""),
        model_name=row.model_name,
        brand_name=row.brand_name,
        claim_text=str(row.clean_claim_text or ""),
        raw_claim_text=row.raw_claim_text,
        source_claim_key=f"clean:{row.clean_claim_id}",
        claim_seq=row.claim_seq,
    )


def _dedupe_claim_records(records: Sequence[M04CClaimRecord]) -> list[M04CClaimRecord]:
    seen = set()
    result = []
    for record in records:
        key = (record.sku_code, _normalize_claim_text(record.claim_text))
        if key in seen:
            continue
        seen.add(key)
        result.append(record)
    return result


def _normalize_input_source(value: str) -> str:
    normalized = str(value or INPUT_SOURCE_AUTO).strip().lower()
    if normalized not in {INPUT_SOURCE_AUTO, INPUT_SOURCE_EVIDENCE, INPUT_SOURCE_CLEAN, INPUT_SOURCE_RAW}:
        raise ValueError(f"unsupported M04C input_source: {value}")
    return normalized


def _normalize_claim_text(value: Any) -> str:
    return str(value or "").lower().replace(" ", "").replace("_", "").replace("-", "")


def _present_text(value: Any) -> bool:
    return bool(str(value or "").strip())


def _none_if_blank(value: Any) -> str | None:
    text_value = str(value or "").strip()
    return text_value or None


def _sku_allowed(sku_code: str | None, prefix: str | None) -> bool:
    if not sku_code:
        return False
    return not prefix or str(sku_code).startswith(prefix)


def _parse_claim_seq(value: Any) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None


def _source_claim_key(sku_code: str, claim_seq: int | None, claim_text: str, index: int) -> str:
    return "generated:" + stable_hash(
        {"sku_code": sku_code, "claim_seq": claim_seq, "claim_text": claim_text, "index": index},
        version="m04c-source-claim-key-v1",
    )[:40]


def _first_present(values: Iterable[Any]) -> Any | None:
    for value in values:
        if value is not None and str(value).strip():
            return value
    return None


def _claim_confidence(status: str, claim: M04CClaimDefinition) -> Decimal:
    if claim.service_separate:
        return Decimal("0.7000")
    if status == SUPPORT_SUPPORTED:
        return Decimal("0.9200")
    if status == SUPPORT_PARTIAL:
        return Decimal("0.7800")
    if status == SUPPORT_UNSUPPORTED:
        return Decimal("0.6000")
    if status == SUPPORT_NOT_APPLICABLE:
        return Decimal("0.6500")
    return Decimal("0.5000")


def _position_explanation(definition: M04CPositionDefinition, position_source: str, source_codes: set[str]) -> str:
    source_label = "参数支撑卖点" if position_source == POSITION_SUPPORTED else "已声明卖点"
    return f"{source_label}包含 {len(source_codes)} 个标准卖点，归入{definition.position_name}；规则：{definition.rule_summary}。"


def _ratio(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0.000000")
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.000001"))


def _unique_preserve_order(values: Iterable[Any]) -> list[Any]:
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _claim_profile_id(project_id: str, batch_id: str, sku_code: str, taxonomy_version: str, rule_version: str) -> str:
    return stable_hash(
        {"project_id": project_id, "batch_id": batch_id, "sku_code": sku_code, "taxonomy_version": taxonomy_version, "rule_version": rule_version},
        version=M04C_PROFILE_ID_HASH_VERSION,
    )[:120]


def _claim_fact_id(project_id: str, batch_id: str, sku_code: str, source_claim_key: str, claim_code: str, rule_version: str) -> str:
    return stable_hash(
        {"project_id": project_id, "batch_id": batch_id, "sku_code": sku_code, "source_claim_key": source_claim_key, "claim_code": claim_code, "rule_version": rule_version},
        version=M04C_FACT_ID_HASH_VERSION,
    )[:120]


def _dimension_position_id(project_id: str, batch_id: str, sku_code: str, taxonomy_version: str, dimension_code: str, position_source: str, rule_version: str) -> str:
    return stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "sku_code": sku_code,
            "taxonomy_version": taxonomy_version,
            "dimension_code": dimension_code,
            "position_source": position_source,
            "rule_version": rule_version,
        },
        version=M04C_POSITION_ID_HASH_VERSION,
    )[:120]


def _position_coverage_id(project_id: str, batch_id: str, taxonomy_version: str, dimension_code: str, position_code: str, position_source: str, rule_version: str) -> str:
    return stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "taxonomy_version": taxonomy_version,
            "dimension_code": dimension_code,
            "position_code": position_code,
            "position_source": position_source,
            "rule_version": rule_version,
        },
        version=M04C_COVERAGE_ID_HASH_VERSION,
    )[:120]


def _taxonomy_summary(taxonomy: M04CClaimTaxonomy) -> dict[str, Any]:
    return {
        "taxonomy_version": taxonomy.taxonomy_version,
        "product_category": taxonomy.product_category,
        "claims": [
            {
                "claim_code": claim.claim_code,
                "claim_name": claim.claim_name,
                "dimension_code": claim.dimension_code,
                "subtype_code": claim.subtype_code,
                "support_param_codes": list(claim.support_param_codes),
                "service_separate": claim.service_separate,
            }
            for claim in taxonomy.claims
        ],
        "positions": [
            {
                "dimension_code": position.dimension_code,
                "position_code": position.position_code,
                "position_name": position.position_name,
                "position_rank": position.position_rank,
            }
            for position in taxonomy.positions
        ],
    }


def _normalize_payload(model_cls: Any, payload: Any, *, project_id: str, category_code: str) -> dict[str, Any]:
    if hasattr(payload, "to_record_payload"):
        raw_payload = payload.to_record_payload()
    elif isinstance(payload, Mapping):
        raw_payload = dict(payload)
    else:
        raise TypeError("M04C repository payload must be a mapping or provide to_record_payload()")
    raw_payload.setdefault("project_id", project_id)
    raw_payload.setdefault("category_code", category_code)
    model_fields = set(model_cls.__table__.columns.keys())
    return {key: value for key, value in raw_payload.items() if key in model_fields}


def _update_existing(existing: Any, payload: Mapping[str, Any]) -> None:
    primary_keys = {column.name for column in existing.__table__.primary_key.columns}
    immutable_fields = primary_keys | {"created_at"}
    for field_name, field_value in _jsonable(payload).items():
        if field_name in immutable_fields:
            continue
        if hasattr(existing, field_name):
            setattr(existing, field_name, field_value)


def _assert_same_hash(existing: Any, payload: Mapping[str, Any], *, hash_field: str | None, unique_fields: tuple[str, ...], model_name: str) -> None:
    if hash_field is None:
        return
    incoming_hash = payload.get(hash_field)
    existing_hash = getattr(existing, hash_field)
    if incoming_hash != existing_hash:
        unique_key = {field_name: payload.get(field_name) for field_name in unique_fields}
        raise ParamRepositoryHashConflictError(f"{model_name} unique key already exists with different {hash_field}: {unique_key}")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def _blocked_result(
    *,
    project_id: str,
    category_code: str,
    batch_id: str | None,
    run_id: str | None,
    message_cn: str,
    started_at: datetime,
    finished_at: datetime,
) -> Core3ModuleRunResultSchema:
    return Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode.M04C,
        status=Core3RunStatus.BLOCKED,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        output_hash=None,
        warnings=[message_cn],
        review_issues=[],
        downstream_impacts=[],
        summary_json={"project_id": project_id, "category_code": category_code, "batch_id": batch_id, "message_cn": message_cn},
        started_at=started_at,
        finished_at=finished_at,
    )


def _failed_result(
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    started_at: datetime,
    error_code: str,
    message_cn: str,
    error_message: str,
) -> Core3ModuleRunResultSchema:
    return Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode.M04C,
        status=Core3RunStatus.FAILED,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        output_hash=None,
        warnings=[],
        review_issues=[{"severity": "blocker", "message_cn": message_cn, "error": error_message}],
        downstream_impacts=[],
        summary_json={
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "error_code": error_code,
            "message_cn": message_cn,
            "error_message": error_message,
        },
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
    )
