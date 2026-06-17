"""M08.5 business-dimension ontology calibration service."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Sequence

from app.services.core3_real_data.constants import (
    CORE3_M08_5_RULE_VERSION,
    CORE3_M08_5_SEED_VERSION,
    CORE3_M08_5_SERVICE_GUARDRAIL_VERSION,
    CORE3_M08_5_THRESHOLD_VERSION,
    Core3RunStatus,
    M085AllocationPolicy,
    M085BoundaryPolicy,
    M085CalibrationIssueSeverity,
    M085DefinitionStatus,
    M085DimensionType,
    M085MappingLevel,
    M085OntologyVersionStatus,
)
from app.services.core3_real_data.dimension_ontology_repositories import DimensionOntologyRepository, M085InputBundle
from app.services.core3_real_data.dimension_ontology_schemas import (
    M085CalibrationIssueRecord,
    M085CandidateSnapshotRecord,
    M085DimensionDefinitionRecord,
    M085EvidenceAnchorRecord,
    M085MappingRuleRecord,
    M085ServiceResult,
    M085VersionRecord,
)
from app.services.core3_real_data.dimension_ontology_seed_loader import M085DimensionSeed, M085DimensionSeedLoader
from app.services.core3_real_data.hash_utils import stable_hash


D0 = Decimal("0")
D1 = Decimal("1")
SERVICE_CONTEXT_CODE = "SERVICE_FULFILLMENT_ASSURANCE"
SERVICE_CONTEXT_NAME_CN = "服务履约保障"
SERVICE_BATTLEFIELD_CODE = "BF_SERVICE_ASSURANCE"


BATTLEFIELD_V2_RULES: dict[str, dict[str, Any]] = {
    "BF_PREMIUM_PICTURE": {
        "v2_code": "BF_PREMIUM_PICTURE_UPGRADE",
        "name_cn": "高端画质升级战场",
        "definition_cn": "在同尺寸价格池内，依靠 Mini LED/OLED/QLED、亮度、控光、色域、HDR 或画质芯片等高端显示能力参与竞争。",
        "migration_action": "refine",
        "anchor_groups": ("display_picture",),
        "market_pool_fit": {"screen_size_classes": ("mainstream_living", "large_upgrade", "ultra_large_flagship"), "price_positions": ("upper_mainstream", "premium", "flagship")},
    },
    "BF_FAMILY_VIEWING_UPGRADE": {
        "v2_code": "BF_FAMILY_VIEWING_COMFORT",
        "name_cn": "家庭观影舒适战场",
        "definition_cn": "在主流客厅或大屏升级池内，依靠尺寸、画质、音效、系统稳定和多人观看体验参与竞争。",
        "migration_action": "refine",
        "anchor_groups": ("display_picture", "audio_immersion", "smart_easy_use"),
        "market_pool_fit": {"screen_size_classes": ("mainstream_living", "large_upgrade"), "price_positions": ("value", "mainstream", "upper_mainstream")},
    },
    "BF_GAMING_SPORTS": {
        "v2_code": "BF_GAMING_SPORTS_FLUENCY",
        "name_cn": "游戏体育流畅战场",
        "definition_cn": "在可比购买池内，依靠高刷、HDMI 2.1、VRR、ALLM、MEMC、低延迟或运动补偿等流畅能力参与竞争。",
        "migration_action": "refine",
        "anchor_groups": ("motion_gaming",),
        "market_pool_fit": {"screen_size_classes": ("mainstream_living", "large_upgrade"), "price_positions": ("mainstream", "upper_mainstream", "premium")},
    },
    "BF_LARGE_SCREEN_VALUE": {
        "v2_code": "BF_LARGE_SCREEN_VALUE_UPGRADE",
        "name_cn": "大屏换新性价比战场",
        "definition_cn": "在大屏升级池内，依靠大尺寸、价格/英寸、关键配置和补贴促销形成换新价值。",
        "migration_action": "refine",
        "anchor_groups": ("screen_value_market", "display_picture"),
        "market_pool_fit": {"screen_size_classes": ("large_upgrade", "ultra_large_flagship"), "price_positions": ("entry", "value", "mainstream")},
    },
    "BF_FAMILY_EYE_CARE": {
        "v2_code": "BF_EYE_CARE_COMFORT_VIEWING",
        "name_cn": "护眼舒适观看战场",
        "definition_cn": "在长期观看相关购买池内，依靠低蓝光、无频闪、护眼认证、环境光或儿童模式等护眼能力参与竞争。",
        "migration_action": "refine",
        "anchor_groups": ("eye_care",),
        "market_pool_fit": {"screen_size_classes": ("compact_screen", "mainstream_living", "large_upgrade"), "price_positions": ("value", "mainstream", "upper_mainstream")},
    },
    "BF_SENIOR_EASE_OF_USE": {
        "v2_code": "BF_SMART_EASE_EXPERIENCE",
        "name_cn": "智能交互易用战场",
        "definition_cn": "长辈是客群线索，不单独构成产品战场；只有语音、遥控、系统、广告风险、内存存储等智能易用锚点成立时，才并入智能交互易用战场。",
        "migration_action": "merge_to",
        "merged_into": "BF_SMART_SYSTEM_EXPERIENCE",
        "anchor_groups": ("smart_easy_use",),
        "market_pool_fit": {"screen_size_classes": ("compact_screen", "mainstream_living"), "price_positions": ("entry", "value", "mainstream")},
    },
    "BF_SMART_SYSTEM_EXPERIENCE": {
        "v2_code": "BF_SMART_EASE_EXPERIENCE",
        "name_cn": "智能交互易用战场",
        "definition_cn": "在可比购买池内，依靠语音、遥控、系统流畅、内存存储、投屏或少广告等智能易用能力参与竞争。",
        "migration_action": "refine",
        "anchor_groups": ("smart_easy_use",),
        "market_pool_fit": {"screen_size_classes": ("compact_screen", "mainstream_living", "large_upgrade"), "price_positions": ("entry", "value", "mainstream")},
    },
    "BF_CINEMA_AUDIO_IMMERSION": {
        "v2_code": "BF_FAMILY_VIEWING_COMFORT_AUDIO_ANCHOR",
        "name_cn": "音画沉浸锚点",
        "definition_cn": "音效当前先作为家庭观影舒适或超大屏旗舰体验的产品锚点；只有音响功率、声道、杜比/DTS 和评论感知同时充分时，才可恢复为独立战场。",
        "migration_action": "anchor_to",
        "merged_into": "BF_FAMILY_VIEWING_UPGRADE",
        "anchor_groups": ("audio_immersion",),
        "market_pool_fit": {"screen_size_classes": ("mainstream_living", "large_upgrade", "ultra_large_flagship"), "price_positions": ("mainstream", "upper_mainstream", "premium", "flagship")},
    },
    "BF_DESIGN_HOME_FIT": {
        "v2_code": "SPACE_FIT_CONTEXT",
        "name_cn": "空间适配装修语境",
        "definition_cn": "装修、挂装、超薄和空间适配优先作为任务/场景语境；没有独立外观参数和产品锚点时，不进入产品价值战场销量分配。",
        "migration_action": "context_only",
        "anchor_groups": ("screen_value_market",),
        "market_pool_fit": {"screen_size_classes": ("compact_screen", "mainstream_living", "large_upgrade"), "price_positions": ("entry", "value", "mainstream")},
    },
}


@dataclass(frozen=True)
class _SignalStats:
    signal_type: str
    signal_code: str
    signal_name_cn: str
    sentence_count: int = 0
    strong_sentence_count: int = 0
    service_sentence_count: int = 0
    low_value_sentence_count: int = 0
    score_sum: Decimal = D0
    specificity_sum: Decimal = D0
    sku_codes: frozenset[str] = frozenset()
    representative_phrases: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    @property
    def sku_count(self) -> int:
        return len(self.sku_codes)

    @property
    def avg_signal_score(self) -> Decimal:
        if self.sentence_count <= 0:
            return D0
        return _round4(self.score_sum / Decimal(self.sentence_count))

    @property
    def specificity_score(self) -> Decimal:
        if self.sentence_count <= 0:
            return D0
        return _round4(self.specificity_sum / Decimal(self.sentence_count))


@dataclass(frozen=True)
class _DimensionContext:
    dimension_type: str
    dimension_code: str
    base_dimension_code: str | None
    name_cn: str
    definition_cn: str
    seed_row: Mapping[str, Any]
    stats: _SignalStats
    product_anchor_skus: frozenset[str]
    market_anchor_skus: frozenset[str]
    total_skus: int
    native_candidates: tuple[Any, ...] = ()
    native_review_issues: tuple[Any, ...] = ()
    native_alignment_proposals: tuple[Any, ...] = ()
    native_anchor_quality_json: Mapping[str, Any] | None = None
    native_product_anchor_score: Decimal | None = None
    market_pool_profile_json: Mapping[str, Any] | None = None
    product_anchor_profile_json: Mapping[str, Any] | None = None

    @property
    def product_anchor_score(self) -> Decimal:
        if self.native_product_anchor_score is not None:
            return _round4(self.native_product_anchor_score)
        if not self.product_anchor_skus:
            return D0
        return _round4(Decimal(len(self.product_anchor_skus)) / Decimal(max(self.stats.sku_count, 1)))

    @property
    def market_anchor_score(self) -> Decimal:
        if not self.market_anchor_skus:
            return D0
        return _round4(Decimal(len(self.market_anchor_skus)) / Decimal(max(self.stats.sku_count, 1)))


@dataclass(frozen=True)
class _NativeDimensionIndex:
    candidates_by_code: Mapping[str, Any]
    supports_by_native_code: Mapping[str, tuple[Any, ...]]
    alignments_by_seed_code: Mapping[str, tuple[Any, ...]]
    issues_by_object_code: Mapping[str, tuple[Any, ...]]


NATIVE_SIGNAL_RULES: tuple[dict[str, Any], ...] = (
    {
        "code": "picture_quality",
        "name": "画质体验",
        "type": "product_experience",
        "keywords": ("画质", "画面", "清晰", "色彩", "亮度", "HDR", "控光", "黑位", "细腻"),
    },
    {
        "code": "audio_quality",
        "name": "音质体验",
        "type": "product_experience",
        "keywords": ("音质", "音响", "音效", "杜比", "低音", "环绕", "影院"),
    },
    {
        "code": "game_console",
        "name": "游戏主机场景",
        "type": "scene",
        "keywords": ("游戏", "主机", "PS5", "xbox", "高刷", "刷新率", "HDMI", "低延迟", "VRR"),
    },
    {
        "code": "sports_watching",
        "name": "体育赛事观看",
        "type": "scene",
        "keywords": ("体育", "看球", "球赛", "世界杯", "足球", "篮球", "赛事", "运动补偿", "MEMC"),
    },
    {
        "code": "senior_family",
        "name": "长辈家庭使用",
        "type": "person",
        "keywords": ("老人", "父母", "爸妈", "长辈", "老年", "语音", "操作简单"),
    },
    {
        "code": "child_eye_care",
        "name": "儿童护眼使用",
        "type": "person",
        "keywords": ("孩子", "儿童", "小孩", "护眼", "低蓝光", "不伤眼", "眼睛"),
    },
    {
        "code": "installation_service",
        "name": "安装配送服务",
        "type": "service_experience",
        "keywords": ("安装", "配送", "送货", "师傅", "上门", "售后", "挂架", "物流", "客服"),
        "service": True,
    },
    {
        "code": "price_value",
        "name": "价格价值感",
        "type": "motive",
        "keywords": ("性价比", "划算", "优惠", "国补", "补贴", "价格", "便宜", "值"),
    },
    {
        "code": "new_home_decoration",
        "name": "新家装修搭配",
        "type": "scene",
        "keywords": ("新家", "装修", "客厅", "背景墙", "家装", "外观", "超薄", "边框"),
    },
    {
        "code": "system_risk",
        "name": "系统广告风险",
        "type": "risk",
        "keywords": ("广告", "卡顿", "死机", "闪退", "坏点", "做工", "破损"),
    },
)


class DimensionOntologyCalibrationService:
    def __init__(
        self,
        repository: DimensionOntologyRepository,
        seed_loader: M085DimensionSeedLoader | None = None,
    ) -> None:
        self.repository = repository
        self.seed_loader = seed_loader or M085DimensionSeedLoader()

    def run_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        rule_version: str = CORE3_M08_5_RULE_VERSION,
        force_new_version: bool = False,
    ) -> M085ServiceResult:
        self.repository.assert_inputs_ready(batch_id)
        seed = self.seed_loader.load()
        bundle = self.repository.load_input_bundle(batch_id)
        input_fingerprint = _input_fingerprint(bundle, seed, rule_version)
        ontology_version_id = _record_id("m085v", batch_id, input_fingerprint)
        ontology_version = f"tv_core3_ontology_{_short_hash(input_fingerprint)}"

        native_stats = _native_signal_stats(bundle)
        mapped_stats = _mapped_signal_stats(bundle)
        matrix_index = _matrix_index(bundle)
        native_index = _native_dimension_index(bundle)
        dimension_contexts = _dimension_contexts(
            seed,
            mapped_stats,
            matrix_index,
            native_index,
            profiles=bundle.profiles,
            total_skus=len(bundle.profiles),
        )
        definitions = _definition_records(
            contexts=dimension_contexts,
            seed=seed,
            batch_id=batch_id,
            ontology_version_id=ontology_version_id,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
            input_fingerprint=input_fingerprint,
        )
        anchors = _anchor_records(
            definitions=definitions,
            contexts=dimension_contexts,
            seed=seed,
            batch_id=batch_id,
            ontology_version_id=ontology_version_id,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
            input_fingerprint=input_fingerprint,
        )
        mapping_rules = _mapping_rule_records(
            definitions=definitions,
            contexts=dimension_contexts,
            seed=seed,
            batch_id=batch_id,
            ontology_version_id=ontology_version_id,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
            input_fingerprint=input_fingerprint,
        )
        snapshots = _snapshot_records(
            native_stats=native_stats,
            mapped_stats=mapped_stats,
            contexts=dimension_contexts,
            seed=seed,
            batch_id=batch_id,
            ontology_version_id=ontology_version_id,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
            input_fingerprint=input_fingerprint,
            total_skus=len(bundle.profiles),
        )
        issues = _issue_records(
            contexts=dimension_contexts,
            definitions=definitions,
            mapping_rules=mapping_rules,
            seed=seed,
            batch_id=batch_id,
            ontology_version_id=ontology_version_id,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
            input_fingerprint=input_fingerprint,
            total_skus=len(bundle.profiles),
        )
        blocking_count = sum(1 for issue in issues if issue.severity == M085CalibrationIssueSeverity.BLOCKING.value)
        warning_count = sum(1 for issue in issues if issue.severity == M085CalibrationIssueSeverity.WARNING.value)
        status = (
            M085OntologyVersionStatus.BLOCKED.value
            if blocking_count
            else M085OntologyVersionStatus.ACTIVE_WITH_WARNING.value
            if warning_count
            else M085OntologyVersionStatus.ACTIVE.value
        )
        dimension_count = Counter(definition.dimension_type for definition in definitions)
        quality_summary = {
            "issue_count": len(issues),
            "warning_count": warning_count,
            "blocking_count": blocking_count,
            "service_context_count": dimension_count.get(M085DimensionType.SERVICE_CONTEXT.value, 0),
            "product_battlefield_count": dimension_count.get(M085DimensionType.BATTLEFIELD.value, 0),
            "v2_definition_layer": "battlefield_v2_size_price_pool",
            "v2_battlefield_rule_count": len(BATTLEFIELD_V2_RULES),
            "v2_battlefield_migration_counts": dict(
                Counter(str(row.get("migration_action") or "keep") for row in BATTLEFIELD_V2_RULES.values())
            ),
            "native_signal_count": len(native_stats),
            "mapped_signal_count": len(mapped_stats),
            "m08_4_native_candidate_count": len(bundle.native_dimension_candidates),
            "m08_4_alignment_count": len(bundle.native_dimension_alignments),
            "m08_4_review_issue_count": len(bundle.native_dimension_review_issues),
            "m08_4_review_issue_counts": dict(Counter(row.issue_code for row in bundle.native_dimension_review_issues)),
            "force_new_version": force_new_version,
        }
        version = M085VersionRecord(
            ontology_version_id=ontology_version_id,
            project_id=self.repository.project_id,
            category_code=self.repository.category_code.value,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            ontology_version=ontology_version,
            base_seed_version=seed.seed_version,
            base_seed_hash=seed.seed_hash,
            source_profile_batch_hash=input_fingerprint,
            status=status,
            active_from_run_id=run_id,
            dimension_count_json=dict(dimension_count),
            quality_summary_json=quality_summary,
            review_required=bool(issues),
            review_status="review_required" if issues else "auto_pass",
            rule_version=rule_version,
            seed_version=seed.seed_version,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                {
                    "ontology_version": ontology_version,
                    "dimension_count": dict(dimension_count),
                    "quality_summary": quality_summary,
                },
                version="m085_version_result_v1",
            ),
        )

        version_write = self.repository.save_version(version)
        self.repository.supersede_current_versions(batch_id, keep_ontology_version_id=ontology_version_id)
        definition_write = self.repository.save_definitions(definitions)
        anchor_write = self.repository.save_anchors(anchors)
        mapping_write = self.repository.save_mapping_rules(mapping_rules)
        snapshot_write = self.repository.save_snapshots(snapshots)
        issue_write = self.repository.save_issues(issues)

        created_count = sum(
            result.created_count
            for result in (version_write, definition_write, anchor_write, mapping_write, snapshot_write, issue_write)
        )
        warnings = [issue.issue_message_cn for issue in issues if issue.severity != M085CalibrationIssueSeverity.INFO.value]
        run_status = Core3RunStatus.BLOCKED if blocking_count else Core3RunStatus.WARNING if warnings else Core3RunStatus.SUCCESS
        summary = {
            "batch_id": batch_id,
            "rule_version": rule_version,
            "seed_version": seed.seed_version,
            "seed_hash": seed.seed_hash,
            "ontology_version_id": ontology_version_id,
            "ontology_version": ontology_version,
            "definition_count": dict(dimension_count),
            "anchor_count": len(anchors),
            "mapping_rule_count": len(mapping_rules),
            "snapshot_count": len(snapshots),
            "issue_count": len(issues),
            "input_sku_count": len(bundle.profiles),
            "usable_comment_atom_count": len(bundle.comment_atoms),
            "downstream_signal_count": len(bundle.downstream_signals),
            "quality_summary": quality_summary,
            "downstream_support": {
                "M09": "读取 task 定义、锚点和 candidate/profile/allocation 映射",
                "M10": "读取 target_group 定义，避免家庭/长辈/儿童等泛化全量命中",
                "M11": "读取 battlefield 与 service_context，服务履约不进入产品战场分配",
                "M11.6": "后续只对 allocation_eligible 的维度做销量分配",
            },
        }
        return M085ServiceResult(
            version=version,
            definitions=tuple(definitions),
            anchors=tuple(anchors),
            mapping_rules=tuple(mapping_rules),
            snapshots=tuple(snapshots),
            issues=tuple(issues),
            summary=summary,
            warnings=warnings,
            status=run_status,
            input_count=len(bundle.profiles),
            output_count=1 + len(definitions) + len(anchors) + len(mapping_rules) + len(snapshots) + len(issues),
            created_output_count=created_count,
        )


def _input_fingerprint(bundle: M085InputBundle, seed: M085DimensionSeed, rule_version: str) -> str:
    return stable_hash(
        {
            "seed_hash": seed.seed_hash,
            "profile_hashes": sorted(profile.profile_hash for profile in bundle.profiles),
            "matrix_hashes": sorted(matrix.result_hash for matrix in bundle.matrices),
            "comment_atom_hashes": sorted(atom.result_hash for atom in bundle.comment_atoms),
            "downstream_signal_hashes": sorted(signal.result_hash for signal in bundle.downstream_signals),
            "native_dimension_candidate_hashes": sorted(row.result_hash for row in bundle.native_dimension_candidates),
            "native_dimension_support_hashes": sorted(row.result_hash for row in bundle.native_dimension_sku_supports),
            "native_dimension_alignment_hashes": sorted(row.result_hash for row in bundle.native_dimension_alignments),
            "native_dimension_issue_hashes": sorted(row.result_hash for row in bundle.native_dimension_review_issues),
            "rule_version": rule_version,
            "service_guardrail_version": CORE3_M08_5_SERVICE_GUARDRAIL_VERSION,
            "threshold_version": CORE3_M08_5_THRESHOLD_VERSION,
        },
        version="m085_input_fingerprint_v1",
    )


def _native_signal_stats(bundle: M085InputBundle) -> dict[str, _SignalStats]:
    builders: dict[str, dict[str, Any]] = {}
    for rule in NATIVE_SIGNAL_RULES:
        builders[rule["code"]] = {
            "rule": rule,
            "sentence_count": 0,
            "strong_sentence_count": 0,
            "service_sentence_count": 0,
            "low_value_sentence_count": 0,
            "score_sum": D0,
            "specificity_sum": D0,
            "sku_codes": set(),
            "phrases": [],
            "evidence_ids": [],
        }
    for atom in bundle.comment_atoms:
        text = f"{atom.sentence_text or ''} {atom.normalized_sentence_text or ''}"
        for rule in NATIVE_SIGNAL_RULES:
            if not _contains_any(text, rule["keywords"]):
                continue
            row = builders[rule["code"]]
            specificity = _decimal(atom.specificity_score)
            confidence = _decimal(atom.confidence)
            row["sentence_count"] += 1
            row["strong_sentence_count"] += 1 if specificity >= Decimal("0.55") or confidence >= Decimal("0.60") else 0
            row["service_sentence_count"] += 1 if rule.get("service") else 0
            row["low_value_sentence_count"] += 1 if atom.low_value_flag else 0
            row["score_sum"] += max(specificity, confidence)
            row["specificity_sum"] += specificity
            row["sku_codes"].add(atom.sku_code)
            if atom.representative_phrase and len(row["phrases"]) < 5:
                row["phrases"].append(atom.representative_phrase)
            if len(row["evidence_ids"]) < 10:
                row["evidence_ids"].append(atom.comment_evidence_id)
    return {
        code: _SignalStats(
            signal_type=str(row["rule"]["type"]),
            signal_code=code,
            signal_name_cn=str(row["rule"]["name"]),
            sentence_count=int(row["sentence_count"]),
            strong_sentence_count=int(row["strong_sentence_count"]),
            service_sentence_count=int(row["service_sentence_count"]),
            low_value_sentence_count=int(row["low_value_sentence_count"]),
            score_sum=row["score_sum"],
            specificity_sum=row["specificity_sum"],
            sku_codes=frozenset(row["sku_codes"]),
            representative_phrases=tuple(row["phrases"]),
            evidence_ids=tuple(row["evidence_ids"]),
        )
        for code, row in builders.items()
        if row["sentence_count"] > 0
    }


def _mapped_signal_stats(bundle: M085InputBundle) -> dict[tuple[str, str], _SignalStats]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for signal in bundle.downstream_signals:
        key = (signal.signal_type, signal.target_code_hint)
        row = rows.setdefault(
            key,
            {
                "signal_type": signal.signal_type,
                "signal_code": signal.target_code_hint,
                "signal_name_cn": signal.target_name_hint,
                "sentence_count": 0,
                "strong_sentence_count": 0,
                "service_sentence_count": 0,
                "low_value_sentence_count": 0,
                "score_sum": D0,
                "specificity_sum": D0,
                "sku_codes": set(),
                "phrases": [],
                "evidence_ids": [],
            },
        )
        sentence_count = int(signal.sentence_count or signal.usable_sentence_count or signal.mention_count or 0)
        row["sentence_count"] += sentence_count
        row["strong_sentence_count"] += sentence_count if signal.signal_level == "strong" else 0
        row["service_sentence_count"] += sentence_count if signal.service_guardrail_flag else 0
        row["low_value_sentence_count"] += 0
        row["score_sum"] += _decimal(signal.signal_score) * Decimal(max(sentence_count, 1))
        row["specificity_sum"] += _decimal(signal.specificity_avg) * Decimal(max(sentence_count, 1))
        row["sku_codes"].add(signal.sku_code)
        for phrase in signal.representative_phrases or []:
            if phrase and len(row["phrases"]) < 5:
                row["phrases"].append(str(phrase))
        for evidence_id in signal.evidence_ids or []:
            if evidence_id and len(row["evidence_ids"]) < 10:
                row["evidence_ids"].append(str(evidence_id))
    return {
        key: _SignalStats(
            signal_type=str(row["signal_type"]),
            signal_code=str(row["signal_code"]),
            signal_name_cn=str(row["signal_name_cn"]),
            sentence_count=int(row["sentence_count"]),
            strong_sentence_count=int(row["strong_sentence_count"]),
            service_sentence_count=int(row["service_sentence_count"]),
            low_value_sentence_count=int(row["low_value_sentence_count"]),
            score_sum=row["score_sum"],
            specificity_sum=row["specificity_sum"],
            sku_codes=frozenset(row["sku_codes"]),
            representative_phrases=tuple(row["phrases"]),
            evidence_ids=tuple(row["evidence_ids"]),
        )
        for key, row in rows.items()
    }


def _matrix_index(bundle: M085InputBundle) -> dict[str, dict[str, set[str]]]:
    result: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for matrix in bundle.matrices:
        if matrix.missing_flag:
            continue
        feature_code = matrix.feature_code or matrix.sub_domain
        result[str(feature_code)]["sku_codes"].add(matrix.sku_code)
        result[str(matrix.domain)]["sku_codes"].add(matrix.sku_code)
    return result


def _native_dimension_index(bundle: M085InputBundle) -> _NativeDimensionIndex:
    candidates_by_code = {
        str(row.native_dimension_code): row
        for row in bundle.native_dimension_candidates
        if row.native_dimension_code
    }
    supports_by_native_code: dict[str, list[Any]] = defaultdict(list)
    for row in bundle.native_dimension_sku_supports:
        if row.native_dimension_code:
            supports_by_native_code[str(row.native_dimension_code)].append(row)
    alignments_by_seed_code: dict[str, list[Any]] = defaultdict(list)
    for row in bundle.native_dimension_alignments:
        if row.seed_dimension_code:
            alignments_by_seed_code[str(row.seed_dimension_code)].append(row)
    issues_by_object_code: dict[str, list[Any]] = defaultdict(list)
    for row in bundle.native_dimension_review_issues:
        if row.object_code:
            issues_by_object_code[str(row.object_code)].append(row)
    return _NativeDimensionIndex(
        candidates_by_code=candidates_by_code,
        supports_by_native_code={key: tuple(value) for key, value in supports_by_native_code.items()},
        alignments_by_seed_code={key: tuple(value) for key, value in alignments_by_seed_code.items()},
        issues_by_object_code={key: tuple(value) for key, value in issues_by_object_code.items()},
    )


def _v2_anchor_groups(dimension_type: str, dimension_code: str) -> tuple[str, ...]:
    if dimension_type == M085DimensionType.BATTLEFIELD.value:
        return tuple(BATTLEFIELD_V2_RULES.get(dimension_code, {}).get("anchor_groups") or ())
    if dimension_type == M085DimensionType.TASK.value:
        return {
            "TASK_LIVING_ROOM_CINEMA": ("display_picture", "audio_immersion"),
            "TASK_PREMIUM_PICTURE_AV": ("display_picture",),
            "TASK_GAMING_ENTERTAINMENT": ("motion_gaming",),
            "TASK_SPORTS_WATCHING": ("motion_gaming",),
            "TASK_LARGE_SCREEN_REPLACEMENT": ("screen_value_market", "display_picture"),
            "TASK_CHILD_EYE_CARE": ("eye_care",),
            "TASK_SENIOR_EASY_USE": ("smart_easy_use",),
            "TASK_VALUE_PURCHASE": ("screen_value_market",),
            "TASK_NEW_HOME_DECORATION": ("screen_value_market", "smart_easy_use"),
            "TASK_BEDROOM_SECOND_TV": ("screen_value_market", "smart_easy_use", "eye_care"),
        }.get(dimension_code, ())
    if dimension_type == M085DimensionType.TARGET_GROUP.value:
        return {
            "TG_FAMILY_UPGRADE": ("display_picture", "screen_value_market"),
            "TG_AV_QUALITY_SEEKER": ("display_picture", "audio_immersion"),
            "TG_GAMER": ("motion_gaming",),
            "TG_SPORTS_FAN": ("motion_gaming",),
            "TG_SENIOR_FAMILY": ("smart_easy_use",),
            "TG_CHILD_FAMILY": ("eye_care",),
            "TG_VALUE_BUYER": ("screen_value_market",),
            "TG_NEW_HOME_DECORATOR": ("screen_value_market", "smart_easy_use"),
            "TG_BEDROOM_SECOND_TV": ("screen_value_market", "smart_easy_use", "eye_care"),
        }.get(dimension_code, ())
    return ()


def _market_pool_profile(profiles: Sequence[Any], sku_codes: set[str]) -> dict[str, Any]:
    rows = [profile for profile in profiles if not sku_codes or profile.sku_code in sku_codes]
    if not rows:
        return {
            "market_pool_key_counts": {},
            "screen_size_class_counts": {},
            "same_pool_position_summary": {},
            "market_pool_sku_count": 0,
        }
    pool_counts: Counter[str] = Counter()
    size_counts: Counter[str] = Counter()
    price_positions: list[Decimal] = []
    volume_positions: list[Decimal] = []
    amount_positions: list[Decimal] = []
    price_per_inch_positions: list[Decimal] = []
    for profile in rows:
        signal_index = profile.business_signal_index_json or {}
        market_summary = profile.market_summary_json or {}
        pool_key = signal_index.get("market_pool_key") or market_summary.get("market_pool_key")
        if pool_key:
            pool_counts[str(pool_key)] += 1
        size_class = signal_index.get("screen_size_class") or market_summary.get("screen_size_class")
        if size_class:
            size_counts[str(size_class)] += 1
        same_pool_position = signal_index.get("same_pool_position") or {}
        price_positions.extend(_optional_decimal_values(same_pool_position.get("price_percentile"), market_summary.get("same_pool_price_percentile")))
        volume_positions.extend(_optional_decimal_values(same_pool_position.get("volume_percentile"), market_summary.get("same_pool_volume_percentile")))
        amount_positions.extend(_optional_decimal_values(same_pool_position.get("amount_percentile"), market_summary.get("same_pool_amount_percentile")))
        price_per_inch_positions.extend(
            _optional_decimal_values(same_pool_position.get("price_per_inch_percentile"), market_summary.get("price_per_inch_percentile"))
        )
    return {
        "market_pool_key_counts": dict(pool_counts.most_common(10)),
        "screen_size_class_counts": dict(size_counts.most_common()),
        "same_pool_position_summary": {
            "price_percentile_avg": _avg_decimal(price_positions),
            "volume_percentile_avg": _avg_decimal(volume_positions),
            "amount_percentile_avg": _avg_decimal(amount_positions),
            "price_per_inch_percentile_avg": _avg_decimal(price_per_inch_positions),
        },
        "market_pool_sku_count": len(rows),
    }


def _product_anchor_profile(profiles: Sequence[Any], sku_codes: set[str], anchor_groups: tuple[str, ...]) -> dict[str, Any]:
    rows = [profile for profile in profiles if not sku_codes or profile.sku_code in sku_codes]
    group_counts: Counter[str] = Counter()
    strong_counts: Counter[str] = Counter()
    score_sums: dict[str, Decimal] = defaultdict(Decimal)
    for profile in rows:
        signal_index = profile.business_signal_index_json or {}
        product_anchor_index = signal_index.get("product_anchor_index") or {}
        groups = product_anchor_index.get("anchor_groups") or {}
        if not isinstance(groups, Mapping):
            continue
        for group_code, payload in groups.items():
            if anchor_groups and str(group_code) not in anchor_groups:
                continue
            if not isinstance(payload, Mapping):
                continue
            group_counts[str(group_code)] += 1
            score = _decimal(payload.get("overall_score"))
            score_sums[str(group_code)] += score
            if score >= Decimal("0.3000") and payload.get("source_status") not in {"claim_only", "market_only"}:
                strong_counts[str(group_code)] += 1
    return {
        "required_anchor_groups": list(anchor_groups),
        "anchor_group_sku_counts": dict(group_counts.most_common()),
        "strong_anchor_group_sku_counts": dict(strong_counts.most_common()),
        "anchor_group_avg_scores": {
            group_code: str(_round4(score_sums[group_code] / Decimal(max(group_counts[group_code], 1))))
            for group_code in sorted(group_counts)
        },
        "anchor_profile_sku_count": len(rows),
    }


def _dimension_contexts(
    seed: M085DimensionSeed,
    mapped_stats: Mapping[tuple[str, str], _SignalStats],
    matrix_index: Mapping[str, Mapping[str, set[str]]],
    native_index: _NativeDimensionIndex,
    *,
    profiles: Sequence[Any],
    total_skus: int,
) -> list[_DimensionContext]:
    contexts: list[_DimensionContext] = []
    for task in seed.tasks:
        code = str(task["task_code"])
        contexts.append(
            _build_context(
                dimension_type=M085DimensionType.TASK.value,
                dimension_code=code,
                name_cn=str(task["task_name"]),
                definition_cn=str(task["definition"]),
                seed_row=task,
                mapped_stats=mapped_stats,
                matrix_index=matrix_index,
                native_index=native_index,
                profiles=profiles,
                total_skus=total_skus,
            )
        )
    for group in seed.target_groups:
        code = str(group["target_group_code"])
        contexts.append(
            _build_context(
                dimension_type=M085DimensionType.TARGET_GROUP.value,
                dimension_code=code,
                name_cn=str(group["target_group_name"]),
                definition_cn=str(group["definition"]),
                seed_row=group,
                mapped_stats=mapped_stats,
                matrix_index=matrix_index,
                native_index=native_index,
                profiles=profiles,
                total_skus=total_skus,
            )
        )
    for battlefield in seed.battlefields:
        code = str(battlefield["battlefield_code"])
        if code == SERVICE_BATTLEFIELD_CODE:
            contexts.append(
                _build_context(
                    dimension_type=M085DimensionType.SERVICE_CONTEXT.value,
                    dimension_code=SERVICE_CONTEXT_CODE,
                    base_dimension_code=code,
                    name_cn=SERVICE_CONTEXT_NAME_CN,
                    definition_cn="安装、配送、上门、售后、退换等服务履约体验，只解释履约侧面和风险，不进入产品价值战场销量分配。",
                    seed_row=battlefield,
                    mapped_stats=mapped_stats,
                    matrix_index=matrix_index,
                    native_index=native_index,
                    profiles=profiles,
                    total_skus=total_skus,
                )
            )
            continue
        contexts.append(
            _build_context(
                dimension_type=M085DimensionType.BATTLEFIELD.value,
                dimension_code=code,
                name_cn=str(battlefield["battlefield_name"]),
                definition_cn=str(battlefield["definition"]),
                seed_row=battlefield,
                mapped_stats=mapped_stats,
                matrix_index=matrix_index,
                native_index=native_index,
                profiles=profiles,
                total_skus=total_skus,
            )
        )
    return contexts


def _build_context(
    *,
    dimension_type: str,
    dimension_code: str,
    name_cn: str,
    definition_cn: str,
    seed_row: Mapping[str, Any],
    mapped_stats: Mapping[tuple[str, str], _SignalStats],
    matrix_index: Mapping[str, Mapping[str, set[str]]],
    native_index: _NativeDimensionIndex,
    profiles: Sequence[Any],
    total_skus: int,
    base_dimension_code: str | None = None,
) -> _DimensionContext:
    target_codes = {dimension_code}
    if base_dimension_code:
        target_codes.add(base_dimension_code)
    stats = _combine_stats(
        stat
        for (signal_type, target_code), stat in mapped_stats.items()
        if target_code in target_codes or target_code in _mapped_codes(seed_row)
    )
    product_anchor_skus = _sku_union(matrix_index, _product_anchor_codes(seed_row))
    market_anchor_skus = _sku_union(matrix_index, ("market", "price", "sales", "platform", "trend"))
    native_candidates, native_alignments = _native_candidates_for_context(
        native_index,
        dimension_code=dimension_code,
        base_dimension_code=base_dimension_code,
    )
    native_issues = _native_issues_for_candidates(native_index, native_candidates)
    native_anchor_quality = _merge_native_anchor_quality(native_candidates)
    native_product_anchor_score = _native_product_anchor_score(native_candidates)
    native_anchor_skus = _native_product_anchor_skus(native_index, native_candidates)
    if native_anchor_skus:
        product_anchor_skus = set(product_anchor_skus) | native_anchor_skus
    evidence_sku_codes = set(product_anchor_skus) | set(stats.sku_codes)
    if not evidence_sku_codes and market_anchor_skus:
        evidence_sku_codes = set(market_anchor_skus)
    market_pool_profile = _market_pool_profile(profiles, evidence_sku_codes)
    product_anchor_profile = _product_anchor_profile(profiles, evidence_sku_codes, _v2_anchor_groups(dimension_type, dimension_code))
    if stats.sku_count == 0 and total_skus > 0:
        stats = _SignalStats(
            signal_type=dimension_type,
            signal_code=dimension_code,
            signal_name_cn=name_cn,
            sku_codes=frozenset(product_anchor_skus or market_anchor_skus),
        )
    return _DimensionContext(
        dimension_type=dimension_type,
        dimension_code=dimension_code,
        base_dimension_code=base_dimension_code,
        name_cn=name_cn,
        definition_cn=definition_cn,
        seed_row=seed_row,
        stats=stats,
        product_anchor_skus=frozenset(product_anchor_skus),
        market_anchor_skus=frozenset(market_anchor_skus),
        total_skus=total_skus,
        native_candidates=tuple(native_candidates),
        native_review_issues=tuple(native_issues),
        native_alignment_proposals=tuple(native_alignments),
        native_anchor_quality_json=native_anchor_quality,
        native_product_anchor_score=native_product_anchor_score,
        market_pool_profile_json=market_pool_profile,
        product_anchor_profile_json=product_anchor_profile,
    )


def _native_candidates_for_context(
    native_index: _NativeDimensionIndex,
    *,
    dimension_code: str,
    base_dimension_code: str | None,
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    seed_codes = {dimension_code}
    if base_dimension_code:
        seed_codes.add(base_dimension_code)
    alignments: list[Any] = []
    candidates: list[Any] = []
    seen_candidates: set[str] = set()
    for seed_code in seed_codes:
        for alignment in native_index.alignments_by_seed_code.get(seed_code, ()):
            alignments.append(alignment)
            native_code = str(alignment.native_dimension_code or "")
            if not native_code or native_code in seen_candidates:
                continue
            candidate = native_index.candidates_by_code.get(native_code)
            if candidate is None:
                continue
            seen_candidates.add(native_code)
            candidates.append(candidate)
    return tuple(candidates), tuple(alignments)


def _native_issues_for_candidates(native_index: _NativeDimensionIndex, candidates: Sequence[Any]) -> tuple[Any, ...]:
    result: list[Any] = []
    seen_keys: set[str] = set()
    for candidate in candidates:
        for issue in native_index.issues_by_object_code.get(str(candidate.native_dimension_code), ()):
            key = str(getattr(issue, "issue_key", "") or getattr(issue, "native_dimension_issue_id", "") or id(issue))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            result.append(issue)
    return tuple(result)


def _native_product_anchor_score(candidates: Sequence[Any]) -> Decimal | None:
    if not candidates:
        return None
    return max((_decimal(candidate.product_anchor_score) for candidate in candidates), default=D0)


def _native_product_anchor_skus(native_index: _NativeDimensionIndex, candidates: Sequence[Any]) -> set[str]:
    result: set[str] = set()
    for candidate in candidates:
        native_code = str(candidate.native_dimension_code)
        for support in native_index.supports_by_native_code.get(native_code, ()):
            if _decimal(support.product_anchor_score) > D0:
                result.add(str(support.sku_code))
        support_summary = candidate.support_summary_json or {}
        product_anchor_by_sku = support_summary.get("product_anchor_by_sku") or {}
        if isinstance(product_anchor_by_sku, Mapping):
            for sku_code, payload in product_anchor_by_sku.items():
                if isinstance(payload, Mapping) and _decimal(payload.get("score")) > D0:
                    result.add(str(sku_code))
    return result


def _merge_native_anchor_quality(candidates: Sequence[Any]) -> dict[str, Any]:
    if not candidates:
        return {}
    quality_flags: list[str] = []
    numeric_sums: Counter[str] = Counter()
    max_values: dict[str, int] = {}
    candidate_summaries: list[dict[str, Any]] = []
    for candidate in candidates:
        support_summary = candidate.support_summary_json or {}
        quality = support_summary.get("anchor_quality_summary") or {}
        if not isinstance(quality, Mapping):
            continue
        candidate_summaries.append(
            {
                "native_dimension_code": candidate.native_dimension_code,
                "native_dimension_name_cn": candidate.native_dimension_name_cn,
                "product_anchor_score": float(_decimal(candidate.product_anchor_score)),
                "candidate_status": candidate.candidate_status,
                "review_reason": dict(candidate.review_reason_json or {}),
                "anchor_quality_summary": dict(quality),
            }
        )
        quality_flags.extend(str(flag) for flag in quality.get("quality_flags") or [])
        for key in (
            "anchor_sku_count",
            "valid_param_sku_count",
            "valid_claim_sku_count",
            "dirty_param_sku_count",
            "matrix_only_sku_count",
        ):
            numeric_sums[key] += int(quality.get(key) or 0)
        for key in ("covered_sku_count",):
            max_values[key] = max(max_values.get(key, 0), int(quality.get(key) or 0))
    result = {key: int(value) for key, value in numeric_sums.items()}
    result.update(max_values)
    result["quality_flags"] = _unique_preserve_order(quality_flags)
    result["native_candidate_summaries"] = candidate_summaries
    return result


def _definition_records(
    *,
    contexts: Sequence[_DimensionContext],
    seed: M085DimensionSeed,
    batch_id: str,
    ontology_version_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    input_fingerprint: str,
) -> list[M085DimensionDefinitionRecord]:
    records: list[M085DimensionDefinitionRecord] = []
    for context in contexts:
        support_score = _support_score(context)
        definition_status = _definition_status(context, support_score)
        allocation_policy = _allocation_policy(context)
        boundary_policy = _boundary_policy(context)
        review_required = definition_status in {
            M085DefinitionStatus.ACTIVE_WITH_WARNING.value,
            M085DefinitionStatus.REVIEW_REQUIRED.value,
            M085DefinitionStatus.BLOCKED.value,
        }
        payload = {
            "dimension_type": context.dimension_type,
            "dimension_code": context.dimension_code,
            "base_dimension_code": context.base_dimension_code,
            "dimension_name_cn": _dimension_name_cn(context),
            "definition_cn": _calibrated_definition(context),
            "business_question_cn": _business_question(context.dimension_type),
            "include_rule_json": _include_rule(context),
            "exclude_rule_json": _exclude_rule(context),
            "required_evidence_json": _required_evidence(context),
            "optional_evidence_json": _optional_evidence(context),
            "negative_evidence_json": _negative_evidence(context),
            "boundary_policy": boundary_policy,
            "allocation_policy": allocation_policy,
            "candidate_trigger_policy_json": _candidate_policy(context),
            "profile_eligibility_policy_json": _profile_policy(context),
            "downstream_policy_json": _downstream_policy(context),
            "distinctiveness_score": _distinctiveness_placeholder(context),
            "support_score": support_score,
            "sku_coverage_count": context.stats.sku_count,
            "strong_sku_coverage_count": len(context.product_anchor_skus) or _strong_sku_count(context),
            "definition_status": definition_status,
            "review_required": review_required,
            "review_reason_json": _definition_review_reason(context, support_score),
        }
        result_hash = stable_hash(payload, version="m085_definition_result_v1")
        records.append(
            M085DimensionDefinitionRecord(
                dimension_definition_id=_record_id("m085d", ontology_version_id, context.dimension_type, context.dimension_code),
                ontology_version_id=ontology_version_id,
                project_id="",
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                seed_version=seed.seed_version,
                seed_hash=seed.seed_hash,
                input_fingerprint=input_fingerprint,
                result_hash=result_hash,
                **payload,
            )
        )
    return records


def _anchor_records(
    *,
    definitions: Sequence[M085DimensionDefinitionRecord],
    contexts: Sequence[_DimensionContext],
    seed: M085DimensionSeed,
    batch_id: str,
    ontology_version_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    input_fingerprint: str,
) -> list[M085EvidenceAnchorRecord]:
    context_by_code = {context.dimension_code: context for context in contexts}
    records: list[M085EvidenceAnchorRecord] = []
    for definition in definitions:
        context = context_by_code[definition.dimension_code]
        for anchor_type, code, name_cn, role, weight in _seed_anchor_rows(context, seed):
            payload = {
                "anchor_type": anchor_type,
                "anchor_code": code,
                "anchor_name_cn": name_cn,
                "anchor_role": role,
                "polarity": "positive" if role != "exclusion" else "negative",
                "weight": weight,
                "min_sentence_count": 1 if anchor_type in {"native_comment", "comment_topic"} else None,
                "min_sku_count": 1,
                "min_confidence": Decimal("0.3500"),
                "representative_phrase_json": list(context.stats.representative_phrases[:5]),
                "representative_evidence_ids": list(context.stats.evidence_ids[:10]),
                "source_rule_json": {"source": "seed_and_m08_5_calibration", "dimension_code": context.dimension_code},
            }
            result_hash = stable_hash(payload, version="m085_anchor_result_v1")
            records.append(
                M085EvidenceAnchorRecord(
                    dimension_anchor_id=_record_id(
                        "m085a",
                        definition.dimension_definition_id,
                        anchor_type,
                        code,
                        role,
                    ),
                    dimension_definition_id=definition.dimension_definition_id,
                    ontology_version_id=ontology_version_id,
                    project_id="",
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    seed_version=seed.seed_version,
                    seed_hash=seed.seed_hash,
                    input_fingerprint=input_fingerprint,
                    result_hash=result_hash,
                    **payload,
                )
            )
    return records


def _mapping_rule_records(
    *,
    definitions: Sequence[M085DimensionDefinitionRecord],
    contexts: Sequence[_DimensionContext],
    seed: M085DimensionSeed,
    batch_id: str,
    ontology_version_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    input_fingerprint: str,
) -> list[M085MappingRuleRecord]:
    context_by_code = {context.dimension_code: context for context in contexts}
    records: list[M085MappingRuleRecord] = []
    for definition in definitions:
        context = context_by_code[definition.dimension_code]
        for source_type, source_code, source_name_cn, mapping_levels in _mapping_sources(context, seed):
            for mapping_level, strength in mapping_levels:
                payload = {
                    "source_type": source_type,
                    "source_code": source_code,
                    "source_name_cn": source_name_cn,
                    "target_dimension_type": definition.dimension_type,
                    "target_dimension_code": definition.dimension_code,
                    "mapping_level": mapping_level,
                    "mapping_strength": strength,
                    "requires_product_anchor": _requires_product_anchor(definition.dimension_type, mapping_level),
                    "requires_market_anchor": mapping_level == M085MappingLevel.ALLOCATION_ELIGIBLE.value
                    and definition.dimension_type != M085DimensionType.SERVICE_CONTEXT.value,
                    "service_guardrail_flag": definition.dimension_type == M085DimensionType.SERVICE_CONTEXT.value,
                    "low_value_guardrail_flag": True,
                    "rule_expr_json": _mapping_rule_expr(context, mapping_level),
                    "reason_cn": _mapping_reason(context, mapping_level),
                    "active": True,
                }
                result_hash = stable_hash(payload, version="m085_mapping_result_v1")
                records.append(
                    M085MappingRuleRecord(
                        dimension_mapping_rule_id=_record_id(
                            "m085m",
                            ontology_version_id,
                            source_type,
                            source_code,
                            definition.dimension_type,
                            definition.dimension_code,
                            mapping_level,
                        ),
                        ontology_version_id=ontology_version_id,
                        project_id="",
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        rule_version=rule_version,
                        seed_version=seed.seed_version,
                        seed_hash=seed.seed_hash,
                        input_fingerprint=input_fingerprint,
                        result_hash=result_hash,
                        **payload,
                    )
                )
        if definition.dimension_type == M085DimensionType.BATTLEFIELD.value:
            payload = {
                "source_type": "native_comment_signal",
                "source_code": "installation_service",
                "source_name_cn": "安装配送服务",
                "target_dimension_type": definition.dimension_type,
                "target_dimension_code": definition.dimension_code,
                "mapping_level": M085MappingLevel.EXCLUDE.value,
                "mapping_strength": D0,
                "requires_product_anchor": True,
                "requires_market_anchor": False,
                "service_guardrail_flag": True,
                "low_value_guardrail_flag": True,
                "rule_expr_json": {"exclude_keywords": ["安装", "配送", "售后", "物流", "师傅"]},
                "reason_cn": "服务履约只能解释交付体验，不可作为产品价值战场成立或分配依据。",
                "active": True,
            }
            records.append(
                M085MappingRuleRecord(
                    dimension_mapping_rule_id=_record_id(
                        "m085m",
                        ontology_version_id,
                        "native_comment_signal",
                        "installation_service",
                        definition.dimension_type,
                        definition.dimension_code,
                        M085MappingLevel.EXCLUDE.value,
                    ),
                    ontology_version_id=ontology_version_id,
                    project_id="",
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    seed_version=seed.seed_version,
                    seed_hash=seed.seed_hash,
                    input_fingerprint=input_fingerprint,
                    result_hash=stable_hash(payload, version="m085_mapping_result_v1"),
                    **payload,
                )
            )
    return records


def _snapshot_records(
    *,
    native_stats: Mapping[str, _SignalStats],
    mapped_stats: Mapping[tuple[str, str], _SignalStats],
    contexts: Sequence[_DimensionContext],
    seed: M085DimensionSeed,
    batch_id: str,
    ontology_version_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    input_fingerprint: str,
    total_skus: int,
) -> list[M085CandidateSnapshotRecord]:
    records: list[M085CandidateSnapshotRecord] = []
    for stats in native_stats.values():
        records.append(
            _snapshot_record(
                stats,
                snapshot_type="native_signal",
                seed=seed,
                batch_id=batch_id,
                ontology_version_id=ontology_version_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                input_fingerprint=input_fingerprint,
                total_skus=total_skus,
            )
        )
    for stats in mapped_stats.values():
        records.append(
            _snapshot_record(
                stats,
                snapshot_type="mapped_dimension",
                seed=seed,
                batch_id=batch_id,
                ontology_version_id=ontology_version_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                input_fingerprint=input_fingerprint,
                total_skus=total_skus,
            )
        )
    for context in contexts:
        records.append(
            _snapshot_record(
                context.stats,
                snapshot_type="seed_dimension",
                seed=seed,
                batch_id=batch_id,
                ontology_version_id=ontology_version_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                input_fingerprint=input_fingerprint,
                total_skus=total_skus,
                signal_type=context.dimension_type,
                signal_code=context.dimension_code,
                signal_name=context.name_cn,
            )
        )
    return records


def _snapshot_record(
    stats: _SignalStats,
    *,
    snapshot_type: str,
    seed: M085DimensionSeed,
    batch_id: str,
    ontology_version_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    input_fingerprint: str,
    total_skus: int,
    signal_type: str | None = None,
    signal_code: str | None = None,
    signal_name: str | None = None,
) -> M085CandidateSnapshotRecord:
    payload = {
        "snapshot_type": snapshot_type,
        "signal_type": signal_type or stats.signal_type,
        "signal_code": signal_code or stats.signal_code,
        "signal_name_cn": signal_name or stats.signal_name_cn,
        "sentence_count": stats.sentence_count,
        "sku_count": stats.sku_count,
        "strong_sentence_count": stats.strong_sentence_count,
        "service_sentence_count": stats.service_sentence_count,
        "low_value_sentence_count": stats.low_value_sentence_count,
        "avg_signal_score": stats.avg_signal_score,
        "coverage_ratio": _ratio(stats.sku_count, total_skus),
        "specificity_score": stats.specificity_score,
        "distribution_json": {
            "top_sku_codes": sorted(stats.sku_codes)[:20],
            "representative_phrases": list(stats.representative_phrases[:5]),
        },
        "representative_evidence_ids": list(stats.evidence_ids[:10]),
    }
    return M085CandidateSnapshotRecord(
        candidate_snapshot_id=_record_id(
            "m085s",
            ontology_version_id,
            snapshot_type,
            payload["signal_type"],
            payload["signal_code"],
        ),
        ontology_version_id=ontology_version_id,
        project_id="",
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        rule_version=rule_version,
        seed_version=seed.seed_version,
        seed_hash=seed.seed_hash,
        input_fingerprint=input_fingerprint,
        result_hash=stable_hash(payload, version="m085_snapshot_result_v1"),
        **payload,
    )


def _issue_records(
    *,
    contexts: Sequence[_DimensionContext],
    definitions: Sequence[M085DimensionDefinitionRecord],
    mapping_rules: Sequence[M085MappingRuleRecord],
    seed: M085DimensionSeed,
    batch_id: str,
    ontology_version_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    input_fingerprint: str,
    total_skus: int,
) -> list[M085CalibrationIssueRecord]:
    issues: list[M085CalibrationIssueRecord] = []
    definition_by_code = {definition.dimension_code: definition for definition in definitions}
    for context in contexts:
        coverage_ratio = _ratio(context.stats.sku_count, total_skus)
        strong_ratio = _ratio(_strong_sku_count(context), max(context.stats.sku_count, 1))
        if (
            context.dimension_type in {M085DimensionType.TASK.value, M085DimensionType.TARGET_GROUP.value, M085DimensionType.BATTLEFIELD.value}
            and coverage_ratio > Decimal("0.7000")
            and strong_ratio < Decimal("0.3500")
            and context.product_anchor_score < Decimal("0.5000")
        ):
            issues.append(
                _issue_record(
                    seed=seed,
                    batch_id=batch_id,
                    ontology_version_id=ontology_version_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    input_fingerprint=input_fingerprint,
                    issue_scope="dimension",
                    dimension_type=context.dimension_type,
                    dimension_code=context.dimension_code,
                    issue_code="dimension_overbroad",
                    severity=M085CalibrationIssueSeverity.WARNING.value,
                    message=f"{context.name_cn} 覆盖 SKU 比例偏高，但强产品锚点不足，后续只能作为候选或需收紧。",
                    evidence={"coverage_ratio": str(coverage_ratio), "strong_ratio": str(strong_ratio)},
                    suggested_action="收紧该维度的必需参数、卖点或场景证据，避免所有 SKU 同时命中。",
                )
            )
        if _has_product_anchor_missing(context):
            issues.append(
                _issue_record(
                    seed=seed,
                    batch_id=batch_id,
                    ontology_version_id=ontology_version_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    input_fingerprint=input_fingerprint,
                    issue_scope="dimension",
                    dimension_type=context.dimension_type,
                    dimension_code=context.dimension_code,
                    issue_code="missing_product_anchor",
                    severity=M085CalibrationIssueSeverity.WARNING.value,
                    message=f"{context.name_cn} 当前缺少参数或卖点产品锚点，不能直接进入产品战场销量分配。",
                    evidence={"mapped_anchor_codes": sorted(_product_anchor_codes(context.seed_row))},
                    suggested_action="补充产品参数/卖点证据，或将该维度保留为候选触发。",
                )
            )
        elif _has_product_anchor_weak_signal(context):
            issues.append(
                _issue_record(
                    seed=seed,
                    batch_id=batch_id,
                    ontology_version_id=ontology_version_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    input_fingerprint=input_fingerprint,
                    issue_scope="dimension",
                    dimension_type=context.dimension_type,
                    dimension_code=context.dimension_code,
                    issue_code="product_anchor_weak",
                    severity=M085CalibrationIssueSeverity.WARNING.value,
                    message=f"{context.name_cn} 存在产品锚点偏弱的原生候选，需要限制其进入分配。",
                    evidence={
                        "native_product_anchor_score": str(context.product_anchor_score),
                        "native_anchor_quality": _native_quality_payload(context),
                        "allocation_block_reasons": sorted(_allocation_block_reasons(context)),
                    },
                    suggested_action="保留干净强候选；弱候选只作为候选触发或人工复核，不直接进入销量分配。",
                )
            )
        if _has_param_mapping_suspect_signal(context):
            blocks_allocation = "param_mapping_suspect" in _allocation_block_reasons(context)
            issues.append(
                _issue_record(
                    seed=seed,
                    batch_id=batch_id,
                    ontology_version_id=ontology_version_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    input_fingerprint=input_fingerprint,
                    issue_scope="dimension",
                    dimension_type=context.dimension_type,
                    dimension_code=context.dimension_code,
                    issue_code="param_mapping_suspect",
                    severity=M085CalibrationIssueSeverity.WARNING.value,
                    message=(
                        f"{context.name_cn} 存在参数映射可疑，当前不能进入销量分配。"
                        if blocks_allocation
                        else f"{context.name_cn} 存在部分参数映射可疑，已限制相关锚点进入分配。"
                    ),
                    evidence={
                        "native_issue_codes": sorted(_native_issue_codes(context)),
                        "native_anchor_quality": _native_quality_payload(context),
                        "suspect_anchor_codes": sorted(_suspect_anchor_codes(context)),
                        "allocation_block_reasons": sorted(_allocation_block_reasons(context)),
                    },
                    suggested_action="复核 M03 参数映射和 M08.4 产品锚点；有干净强候选时只限制可疑锚点，不阻断整个战场。",
                )
            )
    if SERVICE_CONTEXT_CODE in definition_by_code:
        issues.append(
            _issue_record(
                seed=seed,
                batch_id=batch_id,
                ontology_version_id=ontology_version_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                input_fingerprint=input_fingerprint,
                issue_scope="service_guardrail",
                dimension_type=M085DimensionType.SERVICE_CONTEXT.value,
                dimension_code=SERVICE_CONTEXT_CODE,
                issue_code="service_dimension_should_be_context",
                severity=M085CalibrationIssueSeverity.INFO.value,
                message="服务保障已从产品价值战场剥离为服务履约上下文，不参与产品战场销量分配。",
                evidence={"base_dimension_code": SERVICE_BATTLEFIELD_CODE},
                suggested_action="在 M15 报告中作为履约体验展示，不作为产品价值战场。",
            )
        )
    for rule in mapping_rules:
        if (
            rule.target_dimension_type == M085DimensionType.BATTLEFIELD.value
            and rule.mapping_level == M085MappingLevel.ALLOCATION_ELIGIBLE.value
            and rule.mapping_strength < Decimal("0.5500")
        ):
            issues.append(
                _issue_record(
                    seed=seed,
                    batch_id=batch_id,
                    ontology_version_id=ontology_version_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    input_fingerprint=input_fingerprint,
                    issue_scope="mapping",
                    dimension_type=rule.target_dimension_type,
                    dimension_code=rule.target_dimension_code,
                    source_type=rule.source_type,
                    source_code=rule.source_code,
                    issue_code="weak_signal_allocatable",
                    severity=M085CalibrationIssueSeverity.WARNING.value,
                    message="发现弱线索被标记为可分配，后续应降级为候选触发。",
                    evidence={"mapping_strength": str(rule.mapping_strength)},
                    suggested_action="把该映射从 allocation_eligible 降级为 candidate_trigger 或 profile_eligible。",
                )
            )
    issues.extend(
        _overlap_issues(
            contexts=contexts,
            seed=seed,
            batch_id=batch_id,
            ontology_version_id=ontology_version_id,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
            input_fingerprint=input_fingerprint,
        )
    )
    return issues


def _issue_record(
    *,
    seed: M085DimensionSeed,
    batch_id: str,
    ontology_version_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    input_fingerprint: str,
    issue_scope: str,
    issue_code: str,
    severity: str,
    message: str,
    evidence: dict[str, Any],
    suggested_action: str,
    dimension_type: str | None = None,
    dimension_code: str | None = None,
    source_type: str | None = None,
    source_code: str | None = None,
) -> M085CalibrationIssueRecord:
    payload = {
        "issue_scope": issue_scope,
        "dimension_type": dimension_type,
        "dimension_code": dimension_code,
        "source_type": source_type,
        "source_code": source_code,
        "issue_code": issue_code,
        "severity": severity,
        "issue_message_cn": message,
        "evidence_json": evidence,
        "suggested_action_cn": suggested_action,
        "review_status": "open",
    }
    return M085CalibrationIssueRecord(
        calibration_issue_id=_record_id(
            "m085i",
            ontology_version_id,
            issue_scope,
            dimension_type or "",
            dimension_code or "",
            source_type or "",
            source_code or "",
            issue_code,
        ),
        ontology_version_id=ontology_version_id,
        project_id="",
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        rule_version=rule_version,
        seed_version=seed.seed_version,
        seed_hash=seed.seed_hash,
        input_fingerprint=input_fingerprint,
        result_hash=stable_hash(payload, version="m085_issue_result_v1"),
        **payload,
    )


def _overlap_issues(
    *,
    contexts: Sequence[_DimensionContext],
    seed: M085DimensionSeed,
    batch_id: str,
    ontology_version_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    input_fingerprint: str,
) -> list[M085CalibrationIssueRecord]:
    issues: list[M085CalibrationIssueRecord] = []
    for index, left in enumerate(contexts):
        left_anchors = set(_product_anchor_codes(left.seed_row)) | set(_comment_topic_codes(left.seed_row))
        if len(left_anchors) < 2:
            continue
        for right in contexts[index + 1 :]:
            if left.dimension_type != right.dimension_type:
                continue
            right_anchors = set(_product_anchor_codes(right.seed_row)) | set(_comment_topic_codes(right.seed_row))
            if len(right_anchors) < 2:
                continue
            jaccard = _jaccard(left_anchors, right_anchors)
            if jaccard <= Decimal("0.6500"):
                continue
            issues.append(
                _issue_record(
                    seed=seed,
                    batch_id=batch_id,
                    ontology_version_id=ontology_version_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    input_fingerprint=input_fingerprint,
                    issue_scope="overlap",
                    dimension_type=left.dimension_type,
                    dimension_code=left.dimension_code,
                    source_type="dimension",
                    source_code=right.dimension_code,
                    issue_code="low_distinctiveness_overlap",
                    severity=M085CalibrationIssueSeverity.WARNING.value,
                    message=f"{left.name_cn} 与 {right.name_cn} 锚点重叠偏高，可能导致 SKU 同时命中。",
                    evidence={"jaccard": str(jaccard), "overlap_codes": sorted(left_anchors & right_anchors)},
                    suggested_action="收紧两个维度的专属锚点，或在后续画像中增加主次区分。",
                )
            )
    return issues


def _combine_stats(stats: Iterable[_SignalStats]) -> _SignalStats:
    rows = list(stats)
    if not rows:
        return _SignalStats(signal_type="dimension", signal_code="unknown", signal_name_cn="无信号")
    first = rows[0]
    return _SignalStats(
        signal_type=first.signal_type,
        signal_code=first.signal_code,
        signal_name_cn=first.signal_name_cn,
        sentence_count=sum(row.sentence_count for row in rows),
        strong_sentence_count=sum(row.strong_sentence_count for row in rows),
        service_sentence_count=sum(row.service_sentence_count for row in rows),
        low_value_sentence_count=sum(row.low_value_sentence_count for row in rows),
        score_sum=sum((row.score_sum for row in rows), D0),
        specificity_sum=sum((row.specificity_sum for row in rows), D0),
        sku_codes=frozenset().union(*(row.sku_codes for row in rows)),
        representative_phrases=tuple(dict.fromkeys(phrase for row in rows for phrase in row.representative_phrases))[:5],
        evidence_ids=tuple(dict.fromkeys(evidence_id for row in rows for evidence_id in row.evidence_ids))[:10],
    )


def _mapped_codes(seed_row: Mapping[str, Any]) -> set[str]:
    keys = (
        "mapped_task_codes",
        "source_task_codes",
        "core_task_codes",
        "mapped_target_group_codes",
        "default_target_group_codes",
        "battlefield_codes",
        "mapped_battlefield_codes",
        "core_battlefield_codes",
    )
    result: set[str] = set()
    for key in keys:
        result.update(str(code) for code in seed_row.get(key) or () if code)
    return result


def _product_anchor_codes(seed_row: Mapping[str, Any]) -> tuple[str, ...]:
    keys = (
        "positive_claim_codes",
        "mapped_claim_codes",
        "core_claim_codes",
        "positive_param_codes",
        "mapped_param_codes",
        "core_param_codes",
        "supporting_param_codes",
    )
    result: list[str] = []
    for key in keys:
        result.extend(str(code) for code in seed_row.get(key) or () if code)
    return tuple(dict.fromkeys(result))


def _comment_topic_codes(seed_row: Mapping[str, Any]) -> tuple[str, ...]:
    keys = ("comment_topic_codes", "mapped_topic_codes")
    result: list[str] = []
    for key in keys:
        result.extend(str(code) for code in seed_row.get(key) or () if code)
    return tuple(dict.fromkeys(result))


def _sku_union(matrix_index: Mapping[str, Mapping[str, set[str]]], codes: Iterable[str]) -> set[str]:
    result: set[str] = set()
    for code in codes:
        result.update(matrix_index.get(str(code), {}).get("sku_codes", set()))
    return result


def _support_score(context: _DimensionContext) -> Decimal:
    sentence_support = min(Decimal(context.stats.sentence_count) / Decimal("100"), D1)
    sku_support = _ratio(context.stats.sku_count, context.total_skus)
    return _clamp(
        sentence_support * Decimal("0.25")
        + sku_support * Decimal("0.15")
        + context.product_anchor_score * Decimal("0.25")
        + context.market_anchor_score * Decimal("0.10")
        + context.stats.specificity_score * Decimal("0.15")
        + _evidence_diversity(context) * Decimal("0.10")
    )


def _definition_status(context: _DimensionContext, support_score: Decimal) -> str:
    if context.dimension_type == M085DimensionType.SERVICE_CONTEXT.value:
        return M085DefinitionStatus.ACTIVE.value
    if _has_product_anchor_missing(context):
        return M085DefinitionStatus.REVIEW_REQUIRED.value
    if _has_product_anchor_weak_signal(context) or _has_param_mapping_suspect_signal(context):
        return M085DefinitionStatus.ACTIVE_WITH_WARNING.value
    if support_score < Decimal("0.1500"):
        return M085DefinitionStatus.ACTIVE_WITH_WARNING.value
    return M085DefinitionStatus.ACTIVE.value


def _allocation_policy(context: _DimensionContext) -> str:
    if context.dimension_type == M085DimensionType.SERVICE_CONTEXT.value:
        return M085AllocationPolicy.NEVER_ALLOCATE.value
    if context.dimension_type == M085DimensionType.BATTLEFIELD.value:
        if _has_product_anchor_missing(context) or _has_product_anchor_weak(context):
            return M085AllocationPolicy.CANDIDATE_ONLY.value
        if _has_param_mapping_suspect(context):
            return M085AllocationPolicy.REVIEW_REQUIRED.value
        if _v2_allocation_block_reason(context):
            return M085AllocationPolicy.CANDIDATE_ONLY.value
        return M085AllocationPolicy.ELIGIBLE_WHEN_PRODUCT_ANCHOR_PRESENT.value
    return M085AllocationPolicy.ELIGIBLE_WHEN_PROFILE_ELIGIBLE.value


def _boundary_policy(context: _DimensionContext) -> str:
    if context.dimension_type == M085DimensionType.SERVICE_CONTEXT.value:
        return M085BoundaryPolicy.SERVICE_CONTEXT.value
    if context.dimension_code == "BF_DESIGN_HOME_FIT":
        return M085BoundaryPolicy.DIAGNOSTIC_ONLY.value
    if context.dimension_code == "TASK_VALUE_PURCHASE":
        return M085BoundaryPolicy.PURCHASE_CONTEXT.value
    return M085BoundaryPolicy.PRODUCT_VALUE.value


def _dimension_name_cn(context: _DimensionContext) -> str:
    if context.dimension_type == M085DimensionType.BATTLEFIELD.value:
        return str(BATTLEFIELD_V2_RULES.get(context.dimension_code, {}).get("name_cn") or context.name_cn)
    return context.name_cn


def _calibrated_definition(context: _DimensionContext) -> str:
    if context.dimension_type == M085DimensionType.SERVICE_CONTEXT.value:
        return context.definition_cn
    if context.dimension_type == M085DimensionType.BATTLEFIELD.value:
        v2_rule = BATTLEFIELD_V2_RULES.get(context.dimension_code, {})
        base_definition = str(v2_rule.get("definition_cn") or context.definition_cn)
        return f"{base_definition} 校准要求：必须在可比市场池内判断，不能仅凭泛化好评、服务履约或单一评论成立。"
    if context.dimension_type == M085DimensionType.TARGET_GROUP.value:
        return f"{context.definition_cn} 校准要求：客群只解释购买人/使用人，不直接等同产品战场；需由任务、评论人群线索或同池市场表现共同支撑。"
    if context.dimension_type == M085DimensionType.TASK.value:
        return f"{context.definition_cn} 校准要求：任务只解释用户要完成的使用或购买目的，不直接等同目标客群或价值战场；需由评论场景、参数/卖点或市场共现支撑。"
    return f"{context.definition_cn} 校准要求：不能仅凭泛化好评成立，需结合产品参数、卖点、评论场景或市场表现形成可解释证据。"


def _business_question(dimension_type: str) -> str:
    return {
        M085DimensionType.TASK.value: "这台电视主要帮助用户完成什么使用任务？",
        M085DimensionType.TARGET_GROUP.value: "这台电视主要服务哪类购买人群？",
        M085DimensionType.BATTLEFIELD.value: "这台电视靠什么产品价值参与竞争？",
        M085DimensionType.SERVICE_CONTEXT.value: "这台电视交付、安装、售后履约反馈如何？",
    }.get(dimension_type, "这个业务维度回答什么业务问题？")


def _include_rule(context: _DimensionContext) -> dict[str, Any]:
    return {
        "keywords": list(context.seed_row.get("keywords") or ()),
        "aliases": list(context.seed_row.get("aliases") or ()),
        "mapped_codes": sorted(_mapped_codes(context.seed_row)),
        "product_anchor_codes": list(_product_anchor_codes(context.seed_row)),
        "comment_topic_codes": list(_comment_topic_codes(context.seed_row)),
        "native_dimension_codes": [str(candidate.native_dimension_code) for candidate in context.native_candidates],
        "native_issue_codes": sorted(_native_issue_codes(context)),
        "native_anchor_quality": _native_quality_payload(context),
        "v2_definition": _v2_definition_payload(context),
        "market_pool_profile": dict(context.market_pool_profile_json or {}),
        "product_anchor_profile": dict(context.product_anchor_profile_json or {}),
    }


def _exclude_rule(context: _DimensionContext) -> dict[str, Any]:
    exclusions = ["低价值泛化好评", "重复模板评论"]
    if context.dimension_type != M085DimensionType.SERVICE_CONTEXT.value:
        exclusions.append("只包含安装、配送、售后、客服等服务履约反馈")
    return {"exclusions": exclusions}


def _required_evidence(context: _DimensionContext) -> dict[str, Any]:
    if context.dimension_type == M085DimensionType.SERVICE_CONTEXT.value:
        return {"required": ["服务履约评论或 M06 service_signal"], "allocation": "never_allocate"}
    if context.dimension_type == M085DimensionType.BATTLEFIELD.value:
        return {
            "required": ["市场池", "产品参数或卖点锚点", "任务/评论/市场至少一类补强"],
            "market_pool_required_for_profile": True,
            "market_pool_required_for_allocation": True,
            "product_anchor_required": True,
            "min_native_product_anchor_score_for_profile": "0.3000",
            "allocation_blocks": ["product_anchor_missing", "product_anchor_weak", "param_mapping_suspect"],
            "current_native_anchor_quality": _native_quality_payload(context),
            "v2_definition": _v2_definition_payload(context),
        }
    if context.dimension_type == M085DimensionType.TARGET_GROUP.value:
        return {"required": ["人群/场景线索", "任务或市场支撑"], "min_evidence_domains": 2, "direct_product_allocation": False}
    return {"required": ["任务场景线索", "参数/卖点/评论/市场至少一类支撑"], "min_evidence_domains": 1, "direct_product_allocation": False}


def _optional_evidence(context: _DimensionContext) -> dict[str, Any]:
    return {
        "market_anchor_optional": True,
        "comment_examples_optional": True,
        "supporting_sku_count": context.stats.sku_count,
        "native_candidate_count": len(context.native_candidates),
        "native_alignment_count": len(context.native_alignment_proposals),
        "market_pool_profile": dict(context.market_pool_profile_json or {}),
        "product_anchor_profile": dict(context.product_anchor_profile_json or {}),
    }


def _negative_evidence(context: _DimensionContext) -> dict[str, Any]:
    return {"risk_terms": ["广告", "卡顿", "坏点", "破损"], "service_only_blocks_product_value": context.dimension_type != M085DimensionType.SERVICE_CONTEXT.value}


def _candidate_policy(context: _DimensionContext) -> dict[str, Any]:
    return {"allow_weak_signal": True, "low_value_comment_allowed": False, "service_signal_allowed": context.dimension_type == M085DimensionType.SERVICE_CONTEXT.value}


def _profile_policy(context: _DimensionContext) -> dict[str, Any]:
    return {
        "min_support_score": "0.3500",
        "requires_product_anchor": context.dimension_type == M085DimensionType.BATTLEFIELD.value,
        "requires_market_pool": context.dimension_type == M085DimensionType.BATTLEFIELD.value,
        "profile_eligible": _profile_allowed(context),
        "allocation_eligible": _allocation_allowed(context),
        "native_issue_codes": sorted(_native_issue_codes(context)),
        "native_anchor_quality": _native_quality_payload(context),
        "market_pool_policy": _market_pool_policy(context),
        "dimension_role_policy": _dimension_role_policy(context),
    }


def _downstream_policy(context: _DimensionContext) -> dict[str, Any]:
    return {
        "candidate_trigger": True,
        "profile_eligible": _profile_allowed(context),
        "allocation_eligible": _allocation_allowed(context),
        "service_context_only": context.dimension_type == M085DimensionType.SERVICE_CONTEXT.value,
        "allocation_block_reasons": sorted(_allocation_block_reasons(context)),
        "v2_definition": _v2_definition_payload(context),
        "dimension_role_policy": _dimension_role_policy(context),
        "sku_relation_limits": _sku_relation_limits(context),
    }


def _v2_definition_payload(context: _DimensionContext) -> dict[str, Any]:
    if context.dimension_type == M085DimensionType.BATTLEFIELD.value:
        v2_rule = dict(BATTLEFIELD_V2_RULES.get(context.dimension_code, {}))
        return {
            "definition_layer_version": "battlefield_v2_size_price_pool",
            "legacy_code": context.dimension_code,
            "legacy_name_cn": context.name_cn,
            "v2_code": v2_rule.get("v2_code") or context.dimension_code,
            "v2_name_cn": v2_rule.get("name_cn") or context.name_cn,
            "migration_action": v2_rule.get("migration_action") or "keep",
            "merged_into": v2_rule.get("merged_into"),
            "anchor_groups": list(v2_rule.get("anchor_groups") or ()),
            "market_pool_fit": dict(v2_rule.get("market_pool_fit") or {}),
            "old_preset_difference": _old_preset_difference(context, v2_rule),
            "service_context_excluded": context.dimension_code != SERVICE_BATTLEFIELD_CODE,
        }
    return {
        "definition_layer_version": "business_dimension_role_v2",
        "dimension_code": context.dimension_code,
        "dimension_role": _dimension_role_policy(context),
        "product_anchor_groups": list(_v2_anchor_groups(context.dimension_type, context.dimension_code)),
        "old_preset_difference": _old_preset_difference(context, {}),
    }


def _old_preset_difference(context: _DimensionContext, v2_rule: Mapping[str, Any]) -> dict[str, Any]:
    if context.dimension_type == M085DimensionType.BATTLEFIELD.value:
        changes: list[str] = []
        if v2_rule.get("name_cn") and v2_rule.get("name_cn") != context.name_cn:
            changes.append("rename_for_business_clarity")
        if v2_rule.get("migration_action") in {"merge_to", "anchor_to", "context_only"}:
            changes.append(str(v2_rule.get("migration_action")))
        if v2_rule.get("market_pool_fit"):
            changes.append("add_size_price_pool_boundary")
        if v2_rule.get("anchor_groups"):
            changes.append("add_product_anchor_group_requirement")
        if context.dimension_code == SERVICE_BATTLEFIELD_CODE:
            changes.append("move_to_service_context")
        return {
            "changed": bool(changes),
            "changes": changes,
            "legacy_definition_cn": context.definition_cn,
            "v2_definition_cn": v2_rule.get("definition_cn") or context.definition_cn,
        }
    if context.dimension_type == M085DimensionType.TARGET_GROUP.value:
        return {
            "changed": True,
            "changes": ["clarify_as_buyer_or_user_segment", "forbid_direct_product_battlefield_allocation"],
            "legacy_definition_cn": context.definition_cn,
        }
    if context.dimension_type == M085DimensionType.TASK.value:
        return {
            "changed": True,
            "changes": ["clarify_as_usage_or_purchase_task", "separate_from_target_group_and_battlefield"],
            "legacy_definition_cn": context.definition_cn,
        }
    return {"changed": False, "changes": [], "legacy_definition_cn": context.definition_cn}


def _market_pool_policy(context: _DimensionContext) -> dict[str, Any]:
    return {
        "market_pool_required_for_profile": context.dimension_type == M085DimensionType.BATTLEFIELD.value,
        "market_pool_required_for_allocation": context.dimension_type == M085DimensionType.BATTLEFIELD.value,
        "available_market_pool_profile": dict(context.market_pool_profile_json or {}),
        "allowed_market_pool_fit": dict(BATTLEFIELD_V2_RULES.get(context.dimension_code, {}).get("market_pool_fit") or {}),
        "service_or_context_dimension": context.dimension_type == M085DimensionType.SERVICE_CONTEXT.value
        or _v2_allocation_block_reason(context) in {"v2_context_only", "v2_merged_to_parent_battlefield", "v2_anchor_to_parent_battlefield"},
    }


def _dimension_role_policy(context: _DimensionContext) -> dict[str, Any]:
    if context.dimension_type == M085DimensionType.BATTLEFIELD.value:
        return {
            "answers": "这款 SKU 在哪个购买池里被比较，靠什么产品价值赢得购买。",
            "not_answers": ["谁在买", "用户要完成什么任务", "服务履约体验", "单一卖点列表"],
            "requires_market_pool": True,
            "requires_product_anchor": True,
        }
    if context.dimension_type == M085DimensionType.TARGET_GROUP.value:
        return {
            "answers": "谁是主要购买人或使用人。",
            "not_answers": ["产品靠什么价值竞争", "具体使用任务", "服务履约体验"],
            "requires_market_pool": False,
            "requires_product_anchor": False,
            "allowed_evidence_roles": ["person_comment", "task_support", "price_channel_market", "service_side_evidence"],
        }
    if context.dimension_type == M085DimensionType.TASK.value:
        return {
            "answers": "用户用这台电视完成什么观看、娱乐、换新或购买任务。",
            "not_answers": ["谁在买", "产品最终主战场", "服务履约体验"],
            "requires_market_pool": False,
            "requires_product_anchor": False,
            "allowed_evidence_roles": ["scene_comment", "claim_param_support", "market_co_occurrence"],
        }
    if context.dimension_type == M085DimensionType.SERVICE_CONTEXT.value:
        return {
            "answers": "交付、安装、售后履约反馈如何。",
            "not_answers": ["产品价值战场", "销量分配战场"],
            "requires_market_pool": False,
            "requires_product_anchor": False,
        }
    return {"answers": "业务维度的候选解释。", "not_answers": [], "requires_market_pool": False, "requires_product_anchor": False}


def _sku_relation_limits(context: _DimensionContext) -> dict[str, Any]:
    if context.dimension_type != M085DimensionType.BATTLEFIELD.value:
        return {"direct_sales_allocation": False}
    return {
        "main_per_sku": 1,
        "secondary_per_sku_max": 2,
        "opportunity_per_sku_max": 3,
        "main_min_weight": "0.5000",
        "secondary_total_max_weight": "0.5000",
        "single_secondary_max_weight": "0.3500",
        "allocation_requires_relation_level": ["main", "secondary"],
        "allocation_requires_market_pool_fit": True,
        "allocation_requires_product_anchor": True,
    }


def _distinctiveness_placeholder(context: _DimensionContext) -> Decimal:
    return _clamp(Decimal("0.5500") + context.stats.specificity_score * Decimal("0.3000"))


def _definition_review_reason(context: _DimensionContext, support_score: Decimal) -> dict[str, Any]:
    reasons: list[str] = []
    if support_score < Decimal("0.1500"):
        reasons.append("当前批次支撑偏弱")
    if _has_product_anchor_missing(context):
        reasons.append("缺少产品参数或卖点锚点")
    if _has_product_anchor_weak_signal(context):
        if "product_anchor_weak" in _allocation_block_reasons(context):
            reasons.append("M08.4 识别到产品锚点偏弱，只能作为候选维度")
        else:
            reasons.append("M08.4 识别到部分产品锚点偏弱，相关锚点已限制进入分配")
    if _has_param_mapping_suspect_signal(context):
        if "param_mapping_suspect" in _allocation_block_reasons(context):
            reasons.append("M08.4 识别到参数映射可疑，可进画像但不能进入销量分配")
        else:
            reasons.append("M08.4 识别到部分参数映射可疑，相关锚点已限制进入分配")
    if context.stats.service_sentence_count > 0 and context.dimension_type != M085DimensionType.SERVICE_CONTEXT.value:
        reasons.append("存在服务履约线索，需要剥离")
    return {
        "reasons": reasons,
        "native_issue_codes": sorted(_native_issue_codes(context)),
        "native_anchor_quality": _native_quality_payload(context),
    }


def _seed_anchor_rows(context: _DimensionContext, seed: M085DimensionSeed) -> list[tuple[str, str, str, str, Decimal]]:
    name_by_claim = {str(item["claim_code"]): str(item["claim_name"]) for item in seed.standard_claims}
    name_by_param = {str(item["param_code"]): str(item["param_name"]) for item in seed.standard_params}
    name_by_topic = {str(item["topic_code"]): str(item["topic_name"]) for item in seed.comment_topics}
    rows: list[tuple[str, str, str, str, Decimal]] = []
    for code in _product_anchor_codes(context.seed_row):
        if code in name_by_claim:
            rows.append(("claim", code, name_by_claim[code], "required" if context.dimension_type == M085DimensionType.BATTLEFIELD.value else "optional", Decimal("0.7000")))
        elif code in name_by_param:
            rows.append(("param", code, name_by_param[code], "required" if context.dimension_type == M085DimensionType.BATTLEFIELD.value else "optional", Decimal("0.7000")))
    for code in _comment_topic_codes(context.seed_row):
        rows.append(("comment_topic", code, name_by_topic.get(code, code), "optional", Decimal("0.4500")))
    if context.dimension_type == M085DimensionType.SERVICE_CONTEXT.value:
        rows.append(("native_comment", "installation_service", "安装配送服务", "required", Decimal("0.9000")))
    rows.append(("seed", context.base_dimension_code or context.dimension_code, context.name_cn, "optional", Decimal("0.3000")))
    return rows


def _mapping_sources(context: _DimensionContext, seed: M085DimensionSeed) -> list[tuple[str, str, str, list[tuple[str, Decimal]]]]:
    name_by_claim = {str(item["claim_code"]): str(item["claim_name"]) for item in seed.standard_claims}
    name_by_param = {str(item["param_code"]): str(item["param_name"]) for item in seed.standard_params}
    name_by_topic = {str(item["topic_code"]): str(item["topic_name"]) for item in seed.comment_topics}
    rows: list[tuple[str, str, str, list[tuple[str, Decimal]]]] = []
    for code in _product_anchor_codes(context.seed_row):
        source_type = "claim_code" if code in name_by_claim else "param_code"
        name = name_by_claim.get(code) or name_by_param.get(code) or code
        if context.dimension_type == M085DimensionType.SERVICE_CONTEXT.value:
            product_mapping_levels = [(M085MappingLevel.CANDIDATE_TRIGGER.value, Decimal("0.4000"))]
        elif context.dimension_type == M085DimensionType.BATTLEFIELD.value:
            product_mapping_levels = _battlefield_product_mapping_levels(context, code)
        else:
            product_mapping_levels = [
                (M085MappingLevel.CANDIDATE_TRIGGER.value, Decimal("0.8500")),
                (M085MappingLevel.PROFILE_ELIGIBLE.value, Decimal("0.8000")),
                (M085MappingLevel.ALLOCATION_ELIGIBLE.value, Decimal("0.7500")),
            ]
        rows.append(
            (
                source_type,
                code,
                name,
                product_mapping_levels,
            )
        )
    for code in _comment_topic_codes(context.seed_row):
        if context.dimension_type == M085DimensionType.SERVICE_CONTEXT.value:
            topic_mapping_levels = [(M085MappingLevel.CANDIDATE_TRIGGER.value, Decimal("0.3000"))]
        elif context.dimension_type == M085DimensionType.BATTLEFIELD.value and not _profile_allowed(context):
            topic_mapping_levels = [(M085MappingLevel.CANDIDATE_TRIGGER.value, Decimal("0.4500"))]
        elif context.dimension_type == M085DimensionType.BATTLEFIELD.value and not _allocation_allowed(context):
            topic_mapping_levels = [
                (M085MappingLevel.CANDIDATE_TRIGGER.value, Decimal("0.5500")),
                (M085MappingLevel.PROFILE_ELIGIBLE.value, Decimal("0.4000")),
            ]
        else:
            topic_mapping_levels = [
                (M085MappingLevel.CANDIDATE_TRIGGER.value, Decimal("0.5500")),
                (M085MappingLevel.PROFILE_ELIGIBLE.value, Decimal("0.4500")),
            ]
        rows.append(
            (
                "comment_topic",
                code,
                name_by_topic.get(code, code),
                topic_mapping_levels,
            )
        )
    if context.dimension_type == M085DimensionType.SERVICE_CONTEXT.value:
        rows.append(
            (
                "native_comment_signal",
                "installation_service",
                "安装配送服务",
                [
                    (M085MappingLevel.CANDIDATE_TRIGGER.value, Decimal("0.9000")),
                    (M085MappingLevel.PROFILE_ELIGIBLE.value, Decimal("0.7500")),
                ],
            )
        )
    return rows


def _battlefield_product_mapping_levels(context: _DimensionContext, source_code: str) -> list[tuple[str, Decimal]]:
    if source_code in _suspect_anchor_codes(context) or source_code in _weak_anchor_codes(context):
        return [(M085MappingLevel.CANDIDATE_TRIGGER.value, Decimal("0.4500"))]
    if not _profile_allowed(context):
        return [(M085MappingLevel.CANDIDATE_TRIGGER.value, Decimal("0.4500"))]
    if not _allocation_allowed(context):
        return [
            (M085MappingLevel.CANDIDATE_TRIGGER.value, Decimal("0.8500")),
            (M085MappingLevel.PROFILE_ELIGIBLE.value, Decimal("0.6500")),
        ]
    return [
        (M085MappingLevel.CANDIDATE_TRIGGER.value, Decimal("0.8500")),
        (M085MappingLevel.PROFILE_ELIGIBLE.value, Decimal("0.8000")),
        (M085MappingLevel.ALLOCATION_ELIGIBLE.value, Decimal("0.7500")),
    ]


def _profile_allowed(context: _DimensionContext) -> bool:
    if context.dimension_type == M085DimensionType.SERVICE_CONTEXT.value:
        return context.stats.sentence_count > 0
    if context.dimension_type != M085DimensionType.BATTLEFIELD.value:
        return True
    if _v2_allocation_block_reason(context) == "v2_context_only":
        return False
    return not (_has_product_anchor_missing(context) or _has_product_anchor_weak(context))


def _allocation_allowed(context: _DimensionContext) -> bool:
    if context.dimension_type == M085DimensionType.SERVICE_CONTEXT.value:
        return False
    if context.dimension_type != M085DimensionType.BATTLEFIELD.value:
        return True
    return not _allocation_block_reasons(context)


def _allocation_block_reasons(context: _DimensionContext) -> set[str]:
    if context.dimension_type != M085DimensionType.BATTLEFIELD.value:
        return set()
    reasons: set[str] = set()
    v2_reason = _v2_allocation_block_reason(context)
    if v2_reason:
        reasons.add(v2_reason)
    if _has_product_anchor_missing(context):
        reasons.add("product_anchor_missing")
    if _has_product_anchor_weak(context):
        reasons.add("product_anchor_weak")
    if _has_param_mapping_suspect(context):
        reasons.add("param_mapping_suspect")
    return reasons


def _v2_allocation_block_reason(context: _DimensionContext) -> str | None:
    if context.dimension_type != M085DimensionType.BATTLEFIELD.value:
        return None
    migration_action = str(BATTLEFIELD_V2_RULES.get(context.dimension_code, {}).get("migration_action") or "")
    if migration_action == "context_only":
        return "v2_context_only"
    if migration_action == "merge_to":
        return "v2_merged_to_parent_battlefield"
    if migration_action == "anchor_to":
        return "v2_anchor_to_parent_battlefield"
    return None


def _has_product_anchor_missing(context: _DimensionContext) -> bool:
    if context.dimension_type != M085DimensionType.BATTLEFIELD.value:
        return False
    if _has_clean_product_anchor(context):
        return False
    issue_codes = _native_issue_codes(context)
    if "product_anchor_missing" in issue_codes or "missing_product_anchor" in issue_codes:
        return True
    if context.native_candidates:
        return all(_candidate_anchor_score(candidate) <= D0 for candidate in context.native_candidates)
    return not context.product_anchor_skus


def _has_product_anchor_weak(context: _DimensionContext) -> bool:
    if context.dimension_type != M085DimensionType.BATTLEFIELD.value:
        return False
    if _has_product_anchor_missing(context):
        return False
    if _has_clean_product_anchor(context):
        return False
    return _has_product_anchor_weak_signal(context)


def _has_product_anchor_weak_signal(context: _DimensionContext) -> bool:
    if context.dimension_type != M085DimensionType.BATTLEFIELD.value:
        return False
    if "product_anchor_weak" in _native_issue_codes(context):
        return True
    if not context.native_candidates:
        return False
    return any(D0 < _candidate_anchor_score(candidate) < Decimal("0.3000") for candidate in context.native_candidates)


def _has_param_mapping_suspect(context: _DimensionContext) -> bool:
    if context.dimension_type != M085DimensionType.BATTLEFIELD.value:
        return False
    if _has_clean_product_anchor(context):
        return False
    return _has_param_mapping_suspect_signal(context)


def _has_param_mapping_suspect_signal(context: _DimensionContext) -> bool:
    if context.dimension_type != M085DimensionType.BATTLEFIELD.value:
        return False
    if "param_mapping_suspect" in _native_issue_codes(context):
        return True
    quality = context.native_anchor_quality_json or {}
    if int(quality.get("dirty_param_sku_count") or 0) > 0:
        return True
    return "param_mapping_suspect" in {str(flag) for flag in quality.get("quality_flags") or []}


def _has_clean_product_anchor(context: _DimensionContext) -> bool:
    return bool(_clean_native_candidates(context))


def _clean_native_candidates(context: _DimensionContext) -> tuple[Any, ...]:
    result: list[Any] = []
    for candidate in context.native_candidates:
        if _candidate_anchor_score(candidate) < Decimal("0.3000"):
            continue
        issue_codes = _candidate_issue_codes(context, candidate)
        if issue_codes & {"product_anchor_missing", "missing_product_anchor", "product_anchor_weak", "param_mapping_suspect"}:
            continue
        quality = _candidate_anchor_quality(candidate)
        if int(quality.get("dirty_param_sku_count") or 0) > 0:
            continue
        if "param_mapping_suspect" in {str(flag) for flag in quality.get("quality_flags") or []}:
            continue
        result.append(candidate)
    return tuple(result)


def _candidate_anchor_score(candidate: Any) -> Decimal:
    return _decimal(getattr(candidate, "product_anchor_score", None))


def _candidate_issue_codes(context: _DimensionContext, candidate: Any) -> set[str]:
    native_code = str(getattr(candidate, "native_dimension_code", "") or "")
    return {
        str(issue.issue_code)
        for issue in context.native_review_issues
        if str(getattr(issue, "object_code", "") or "") == native_code and getattr(issue, "issue_code", None)
    }


def _candidate_anchor_quality(candidate: Any) -> Mapping[str, Any]:
    support_summary = getattr(candidate, "support_summary_json", None) or {}
    quality = support_summary.get("anchor_quality_summary") or {}
    return quality if isinstance(quality, Mapping) else {}


def _suspect_anchor_codes(context: _DimensionContext) -> set[str]:
    result: set[str] = set()
    for candidate in context.native_candidates:
        issue_codes = _candidate_issue_codes(context, candidate)
        quality = _candidate_anchor_quality(candidate)
        quality_flags = {str(flag) for flag in quality.get("quality_flags") or []}
        if "param_mapping_suspect" not in issue_codes and "param_mapping_suspect" not in quality_flags and int(quality.get("dirty_param_sku_count") or 0) <= 0:
            continue
        result.update(_candidate_anchor_codes(candidate, required_flag="param_mapping_suspect"))
    return result - _clean_anchor_codes(context)


def _weak_anchor_codes(context: _DimensionContext) -> set[str]:
    result: set[str] = set()
    for candidate in context.native_candidates:
        if "product_anchor_weak" not in _candidate_issue_codes(context, candidate) and not (
            D0 < _candidate_anchor_score(candidate) < Decimal("0.3000")
        ):
            continue
        result.update(_candidate_anchor_codes(candidate))
    return result - _clean_anchor_codes(context)


def _clean_anchor_codes(context: _DimensionContext) -> set[str]:
    result: set[str] = set()
    for candidate in _clean_native_candidates(context):
        result.update(_candidate_anchor_codes(candidate))
    return result


def _candidate_anchor_codes(candidate: Any, *, required_flag: str | None = None) -> set[str]:
    result: set[str] = set()
    support_summary = getattr(candidate, "support_summary_json", None) or {}
    product_anchor_by_sku = support_summary.get("product_anchor_by_sku") or {}
    if not isinstance(product_anchor_by_sku, Mapping):
        return result
    for payload in product_anchor_by_sku.values():
        if not isinstance(payload, Mapping):
            continue
        for hit_key in ("param_hits", "claim_hits", "matrix_hits"):
            for hit in payload.get(hit_key) or []:
                if not isinstance(hit, Mapping):
                    continue
                anchor_code = hit.get("anchor_code")
                if not anchor_code:
                    continue
                flags = {str(flag) for flag in hit.get("quality_flags") or []}
                if required_flag and required_flag not in flags and hit.get("usable_for_battlefield") is not False:
                    continue
                result.add(str(anchor_code))
    return result


def _native_issue_codes(context: _DimensionContext) -> set[str]:
    return {str(issue.issue_code) for issue in context.native_review_issues if getattr(issue, "issue_code", None)}


def _native_quality_payload(context: _DimensionContext) -> dict[str, Any]:
    quality = dict(context.native_anchor_quality_json or {})
    if quality:
        quality["quality_flags"] = [str(flag) for flag in quality.get("quality_flags") or []]
        quality["native_candidate_summaries"] = list(quality.get("native_candidate_summaries") or [])
    return {
        "native_product_anchor_score": str(context.product_anchor_score),
        "native_candidate_codes": [str(candidate.native_dimension_code) for candidate in context.native_candidates],
        "native_issue_codes": sorted(_native_issue_codes(context)),
        "quality": quality,
        "product_anchor_sku_count": len(context.product_anchor_skus),
    }


def _mapping_rule_expr(context: _DimensionContext, mapping_level: str) -> dict[str, Any]:
    return {
        "dimension_code": context.dimension_code,
        "level": mapping_level,
        "requires_non_low_value_comment": True,
        "service_guardrail": context.dimension_type == M085DimensionType.SERVICE_CONTEXT.value,
        "v2_definition": _v2_definition_payload(context),
        "market_pool_policy": _market_pool_policy(context),
        "dimension_role_policy": _dimension_role_policy(context),
        "native_product_anchor_score": str(context.product_anchor_score),
        "native_issue_codes": sorted(_native_issue_codes(context)),
        "native_anchor_quality": _native_quality_payload(context),
        "profile_eligible": _profile_allowed(context),
        "allocation_eligible": _allocation_allowed(context),
    }


def _mapping_reason(context: _DimensionContext, mapping_level: str) -> str:
    if context.dimension_type == M085DimensionType.SERVICE_CONTEXT.value:
        return "该线索只用于服务履约上下文，不作为产品价值战场销量分配依据。"
    if context.dimension_type == M085DimensionType.BATTLEFIELD.value:
        v2_reason = _v2_allocation_block_reason(context)
        if v2_reason == "v2_context_only":
            return "该旧战场在 v2 中被降级为场景语境，只触发候选或报告说明，不进入产品战场销量分配。"
        if v2_reason == "v2_merged_to_parent_battlefield":
            return "该旧战场在 v2 中合并到父级产品战场，当前只作为父级战场的锚点或客群侧证据。"
        if v2_reason == "v2_anchor_to_parent_battlefield":
            return "该旧战场在 v2 中作为父级战场的产品锚点使用，独立战场需等待更充分音效/产品证据。"
        if _has_product_anchor_missing(context):
            return "M08.4 未找到可用产品参数或卖点锚点，该战场当前只能触发候选，不能进入画像或销量分配。"
        if _has_product_anchor_weak(context):
            return "M08.4 找到的产品锚点偏弱，该战场当前只能触发候选，待补充参数或卖点证据后再进入画像。"
        if _has_product_anchor_weak_signal(context) and mapping_level == M085MappingLevel.CANDIDATE_TRIGGER.value:
            return "该战场包含部分弱产品锚点，弱锚点只触发候选；干净强锚点可继续支撑画像和分配。"
        if _has_param_mapping_suspect(context) and mapping_level == M085MappingLevel.PROFILE_ELIGIBLE.value:
            return "该战场有一定产品锚点，但参数映射可疑，允许进入画像复核，不允许进入销量分配。"
        if _has_param_mapping_suspect(context) and mapping_level == M085MappingLevel.ALLOCATION_ELIGIBLE.value:
            return "参数映射可疑时不可进入销量分配。"
        if _has_param_mapping_suspect_signal(context) and mapping_level == M085MappingLevel.CANDIDATE_TRIGGER.value:
            return "该战场包含部分参数映射可疑锚点，可疑锚点只触发候选，不作为分配依据。"
    if mapping_level == M085MappingLevel.ALLOCATION_ELIGIBLE.value:
        return "该线索必须与产品参数、卖点或市场证据共同满足，才可参与画像和销量分配。"
    return "该线索可触发候选，后续需按本体定义继续校验画像成立条件。"


def _requires_product_anchor(dimension_type: str, mapping_level: str) -> bool:
    return dimension_type == M085DimensionType.BATTLEFIELD.value and mapping_level in {
        M085MappingLevel.PROFILE_ELIGIBLE.value,
        M085MappingLevel.ALLOCATION_ELIGIBLE.value,
    }


def _evidence_diversity(context: _DimensionContext) -> Decimal:
    domains = 0
    if context.stats.sentence_count:
        domains += 1
    if context.product_anchor_skus:
        domains += 1
    if context.market_anchor_skus:
        domains += 1
    return _ratio(domains, 3)


def _strong_sku_count(context: _DimensionContext) -> int:
    if context.native_anchor_quality_json:
        quality = context.native_anchor_quality_json
        valid_anchor_count = int(quality.get("valid_param_sku_count") or 0) + int(quality.get("valid_claim_sku_count") or 0)
        if valid_anchor_count > 0:
            return min(max(valid_anchor_count, len(context.product_anchor_skus)), max(context.stats.sku_count, len(context.product_anchor_skus), 1))
    if context.product_anchor_skus:
        return len(context.product_anchor_skus)
    if context.stats.strong_sentence_count <= 0:
        return 0
    return max(1, min(context.stats.sku_count, context.stats.strong_sentence_count))


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(str(keyword).lower() in lowered for keyword in keywords if keyword)


def _unique_preserve_order(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _ratio(numerator: int | Decimal, denominator: int | Decimal) -> Decimal:
    denominator_decimal = Decimal(str(denominator))
    if denominator_decimal <= 0:
        return D0
    return _round4(Decimal(str(numerator)) / denominator_decimal)


def _jaccard(left: set[str], right: set[str]) -> Decimal:
    if not left or not right:
        return D0
    return _ratio(len(left & right), len(left | right))


def _decimal(value: Any) -> Decimal:
    if value is None:
        return D0
    return Decimal(str(value))


def _optional_decimal_values(*values: Any) -> list[Decimal]:
    result: list[Decimal] = []
    seen: set[str] = set()
    for value in values:
        if value in (None, "", "-"):
            continue
        decimal_value = _decimal(value)
        key = str(decimal_value)
        if key in seen:
            continue
        seen.add(key)
        result.append(decimal_value)
    return result


def _avg_decimal(values: Sequence[Decimal]) -> str | None:
    if not values:
        return None
    return str(_round4(sum(values, D0) / Decimal(len(values))))


def _round4(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _clamp(value: Decimal) -> Decimal:
    if value < D0:
        return D0
    if value > D1:
        return D1
    return _round4(value)


def _record_id(prefix: str, *parts: object) -> str:
    digest = stable_hash({"parts": [str(part) for part in parts]}, version=f"{prefix}_id_v1").split(":")[-1][:32]
    return f"{prefix}_{digest}"


def _short_hash(value: str) -> str:
    return value.split(":")[-1][:12]
