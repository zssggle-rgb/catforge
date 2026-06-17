"""M04a promo claim matcher and entity extractor."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping

from app.services.core3_real_data.base_claim_activation_schemas import (
    ClaimHitSourceType,
    ClaimMatchMethod,
    ClaimReviewStatus,
    StdClaimDefinition,
    StdClaimSeed,
)
from app.services.core3_real_data.constants import (
    CORE3_M04A_RULE_VERSION,
    CORE3_M04A_SEED_VERSION,
    Core3CategoryCode,
    Core3EvidenceStatus,
    Core3EvidenceType,
)
from app.services.core3_real_data.hash_utils import stable_hash


CLAIM_HIT_ID_HASH_VERSION = "m04a-claim-hit-id-v1"
CLAIM_HIT_HASH_VERSION = "m04a-claim-hit-v1"
PROMO_EVIDENCE_TYPES = {
    Core3EvidenceType.PROMO_RAW.value,
    Core3EvidenceType.PROMO_SENTENCE.value,
}
TITLE_HINT_WORDS = {
    "核心定位",
    "功能价值",
    "情感价值",
    "便捷体验",
    "差异化定位",
    "行业地位",
}
ABSTRACT_PROMO_TERMS = {
    "旗舰体验",
    "行业领先",
    "震撼升级",
    "全面升级",
    "卓越体验",
    "领先科技",
    "高端旗舰",
}
ENTITY_CLAIM_MAP: dict[str, set[str]] = {
    "CLAIM_MINI_LED_BACKLIGHT": {"display_technology", "backlight_control"},
    "CLAIM_OLED_SELF_LIT": {"display_technology", "backlight_control"},
    "CLAIM_QLED_WIDE_COLOR": {"display_technology", "picture_quality"},
    "CLAIM_HIGH_BRIGHTNESS_HDR": {"picture_quality"},
    "CLAIM_FINE_LOCAL_DIMMING": {"backlight_control", "picture_quality"},
    "CLAIM_HIGH_REFRESH_RATE": {"gaming_connection", "motion"},
    "CLAIM_GAMING_LOW_LATENCY": {"gaming_connection"},
    "CLAIM_HDMI_2_1_GAMING": {"gaming_connection"},
    "CLAIM_SPORTS_MOTION_SMOOTH": {"motion", "gaming_connection"},
    "CLAIM_EYE_CARE_COMFORT": {"eye_care"},
    "CLAIM_SMART_VOICE_EASE": {"smart"},
    "CLAIM_ELDER_FRIENDLY_SMART": {"smart"},
    "CLAIM_NO_AD_OR_CLEAN_SYSTEM": {"smart"},
    "CLAIM_IMMERSIVE_AUDIO": {"audio"},
    "CLAIM_DOLBY_CINEMA_AUDIO": {"audio"},
    "CLAIM_THIN_DESIGN": {"design"},
    "CLAIM_INSTALLATION_SERVICE_ASSURANCE": {"service"},
}
ENTITY_MATCH_MIN_SCORE = Decimal("0.4500")
CLOSE_MATCH_DELTA = Decimal("0.2000")
SPECIFIC_CLAIM_REQUIRED_TERMS: dict[str, set[str]] = {
    "CLAIM_ELDER_FRIENDLY_SMART": {"老人", "长辈", "爸妈", "父母", "适老", "老人模式", "长辈模式"},
    "CLAIM_NO_AD_OR_CLEAN_SYSTEM": {"无广告", "少广告", "开机广告", "清爽系统", "纯净系统"},
}


@dataclass(frozen=True)
class ExtractedClaimEntities:
    technology_entities: list[str]
    picture_entities: list[str]
    backlight_entities: list[str]
    gaming_entities: list[str]
    motion_entities: list[str]
    eye_care_entities: list[str]
    audio_entities: list[str]
    smart_entities: list[str]
    design_entities: list[str]
    service_entities: list[str]
    numeric_entities: list[dict[str, Any]]
    entity_quality: dict[str, bool]

    def to_json(self) -> dict[str, Any]:
        return {
            "technology_entities": self.technology_entities,
            "picture_entities": self.picture_entities,
            "backlight_entities": self.backlight_entities,
            "gaming_entities": self.gaming_entities,
            "motion_entities": self.motion_entities,
            "eye_care_entities": self.eye_care_entities,
            "audio_entities": self.audio_entities,
            "smart_entities": self.smart_entities,
            "design_entities": self.design_entities,
            "service_entities": self.service_entities,
            "numeric_entities": self.numeric_entities,
            "entity_quality": self.entity_quality,
        }

    def categories(self) -> set[str]:
        categories: set[str] = set()
        if self.technology_entities:
            categories.add("display_technology")
        if self.picture_entities:
            categories.add("picture_quality")
        if self.backlight_entities:
            categories.add("backlight_control")
        if self.gaming_entities:
            categories.add("gaming_connection")
        if self.motion_entities:
            categories.add("motion")
        if self.eye_care_entities:
            categories.add("eye_care")
        if self.audio_entities:
            categories.add("audio")
        if self.smart_entities:
            categories.add("smart")
        if self.design_entities:
            categories.add("design")
        if self.service_entities:
            categories.add("service")
        return categories


@dataclass(frozen=True)
class ClaimHitDraft:
    claim_hit_id: str
    project_id: str
    category_code: str
    batch_id: str
    run_id: str | None
    module_run_id: str | None
    sku_code: str
    model_name: str | None
    claim_code: str
    claim_name: str
    claim_group: str
    hit_source_type: str
    source_sentence_key: str
    claim_seq: int | None
    sentence_seq: int | None
    claim_fragment: str | None
    matched_keywords: list[str]
    title_hint: str | None
    extracted_entity_json: dict[str, Any]
    matched_param_codes: list[str]
    match_method: str
    promo_evidence_ids: list[str]
    param_evidence_ids: list[str]
    quality_evidence_ids: list[str]
    match_confidence: Decimal
    quality_flags: list[str]
    review_required: bool
    review_status: str
    hit_hash: str
    seed_version: str
    rule_version: str

    def to_record_payload(self) -> dict[str, Any]:
        return {
            "claim_hit_id": self.claim_hit_id,
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "module_run_id": self.module_run_id,
            "sku_code": self.sku_code,
            "model_name": self.model_name,
            "claim_code": self.claim_code,
            "claim_name": self.claim_name,
            "claim_group": self.claim_group,
            "hit_source_type": self.hit_source_type,
            "source_sentence_key": self.source_sentence_key,
            "claim_seq": self.claim_seq,
            "sentence_seq": self.sentence_seq,
            "claim_fragment": self.claim_fragment,
            "matched_keywords": self.matched_keywords,
            "title_hint": self.title_hint,
            "extracted_entity_json": self.extracted_entity_json,
            "matched_param_codes": self.matched_param_codes,
            "match_method": self.match_method,
            "promo_evidence_ids": self.promo_evidence_ids,
            "param_evidence_ids": self.param_evidence_ids,
            "quality_evidence_ids": self.quality_evidence_ids,
            "match_confidence": self.match_confidence,
            "quality_flags": self.quality_flags,
            "review_required": self.review_required,
            "review_status": self.review_status,
            "hit_hash": self.hit_hash,
            "seed_version": self.seed_version,
            "rule_version": self.rule_version,
        }


class ClaimEntityExtractor:
    """Extract technical and numeric entities from promo text."""

    def extract(self, text: str) -> ExtractedClaimEntities:
        clean_text = text.strip()
        numeric_entities = _extract_numeric_entities(clean_text)
        return ExtractedClaimEntities(
            technology_entities=_find_terms(clean_text, ["Mini LED", "MiniLED", "OLED", "QLED", "ULED", "量子点"]),
            picture_entities=_find_terms(clean_text, ["HDR", "XDR", "高亮", "色域", "广色域", "控黑", "纯黑"]),
            backlight_entities=_find_terms(clean_text, ["分区", "局部调光", "分区控光", "光晕控制", "背光"]),
            gaming_entities=_find_terms(clean_text, ["HDMI2.1", "HDMI 2.1", "VRR", "ALLM", "低延迟", "游戏模式"]),
            motion_entities=_find_terms(clean_text, ["高刷", "刷新率", "MEMC", "运动补偿", "看球不卡", "体育"]),
            eye_care_entities=_find_terms(clean_text, ["低蓝光", "无频闪", "高频调光", "护眼", "防眩光"]),
            audio_entities=_find_terms(clean_text, ["Dolby", "杜比", "Atmos", "声道", "低音", "音响", "环绕"]),
            smart_entities=_find_terms(clean_text, ["AI", "语音", "远场语音", "内存", "系统流畅", "无广告", "适老"]),
            design_entities=_find_terms(clean_text, ["超薄", "全面屏", "美学", "挂墙", "金属机身"]),
            service_entities=_find_terms(clean_text, ["安装", "送装", "售后", "送货", "上门", "服务"]),
            numeric_entities=numeric_entities,
            entity_quality={
                "abstract_promo_only": _contains_any(clean_text, ABSTRACT_PROMO_TERMS)
                and not numeric_entities
                and not _has_specific_entity(clean_text),
                "unit_uncertain": any(entity.get("unit_uncertain") for entity in numeric_entities),
                "scope_uncertain": _contains_any(clean_text, ["至高", "最高", "峰值", "瞬时", "动态"]),
            },
        )


class PromoClaimMatcher:
    """Match promo evidence records to standard claim definitions."""

    def __init__(
        self,
        *,
        project_id: str,
        batch_id: str,
        seed: StdClaimSeed,
        category_code: Core3CategoryCode | str = Core3CategoryCode.TV,
        run_id: str | None = None,
        module_run_id: str | None = None,
        seed_version: str = CORE3_M04A_SEED_VERSION,
        rule_version: str = CORE3_M04A_RULE_VERSION,
        entity_extractor: ClaimEntityExtractor | None = None,
    ) -> None:
        self.project_id = project_id
        self.batch_id = batch_id
        self.category_code = _enum_value(category_code)
        self.run_id = run_id
        self.module_run_id = module_run_id
        self.seed = seed
        self.seed_version = seed_version
        self.rule_version = rule_version
        self.entity_extractor = entity_extractor or ClaimEntityExtractor()

    def match(self, evidence_records: Iterable[Any]) -> list[ClaimHitDraft]:
        hits: list[ClaimHitDraft] = []
        for evidence_record in evidence_records:
            if not _is_current_promo_evidence(evidence_record):
                continue
            text = _promo_text(evidence_record)
            if not text:
                continue
            entities = self.entity_extractor.extract(text)
            scored_matches = self._score_record(evidence_record, text, entities)
            close_review_codes = _close_review_codes(scored_matches)
            for score in scored_matches:
                if score.confidence <= Decimal("0"):
                    continue
                hits.append(self._build_hit(evidence_record, text, entities, score, score.claim_code in close_review_codes))
        return sorted(hits, key=lambda hit: (hit.sku_code, hit.source_sentence_key, hit.claim_code))

    def _score_record(
        self,
        evidence_record: Any,
        text: str,
        entities: ExtractedClaimEntities,
    ) -> list["_ClaimMatchScore"]:
        scores: list[_ClaimMatchScore] = []
        title_hint = _title_hint(evidence_record)
        for claim in self.seed.standard_claims:
            exact_aliases = _matched_terms(text, claim.aliases)
            promo_keywords = _matched_terms(text, claim.promo_keywords)
            keywords = _matched_terms(text, claim.keywords)
            matched_keywords = _unique_preserve_order([*exact_aliases, *promo_keywords, *keywords])
            entity_categories = entities.categories() & ENTITY_CLAIM_MAP.get(claim.claim_code, set())
            if not _has_required_claim_context(text, claim.claim_code):
                matched_keywords = []
                promo_keywords = []
                keywords = []
                entity_categories = set()
            title_hint_matched = bool(title_hint and _contains_any(title_hint, TITLE_HINT_WORDS))
            abstract_only = entities.entity_quality["abstract_promo_only"]

            confidence = Decimal("0.0000")
            match_method: ClaimMatchMethod | None = None
            quality_flags: list[str] = []
            if exact_aliases:
                confidence = Decimal("0.8800")
                match_method = ClaimMatchMethod.EXACT_ALIAS
            elif promo_keywords or keywords:
                confidence = Decimal("0.7600")
                match_method = ClaimMatchMethod.KEYWORD
            elif entity_categories:
                confidence = ENTITY_MATCH_MIN_SCORE
                match_method = ClaimMatchMethod.ENTITY

            if entity_categories and confidence > Decimal("0"):
                confidence = min(Decimal("0.9500"), confidence + Decimal("0.0700"))
            if title_hint_matched and confidence > Decimal("0"):
                confidence = min(Decimal("0.8500"), confidence + Decimal("0.0400"))
                quality_flags.append("title_hint_weak")
            elif title_hint and confidence <= Decimal("0"):
                quality_flags.append("title_hint_only_ignored")
            if abstract_only and confidence > Decimal("0"):
                confidence = min(confidence, Decimal("0.4200"))
                quality_flags.append("abstract_promo_only")
            if entities.entity_quality["scope_uncertain"] and confidence > Decimal("0"):
                confidence = min(confidence, Decimal("0.7800"))
                quality_flags.append("scope_uncertain")
            if entities.entity_quality["unit_uncertain"] and confidence > Decimal("0"):
                confidence = min(confidence, Decimal("0.7000"))
                quality_flags.append("unit_uncertain")

            if confidence > Decimal("0") and match_method is not None:
                scores.append(
                    _ClaimMatchScore(
                        claim=claim,
                        claim_code=claim.claim_code,
                        matched_keywords=matched_keywords,
                        matched_param_codes=claim.mapped_param_codes,
                        match_method=match_method.value,
                        match_confidence=confidence.quantize(Decimal("0.0001")),
                        quality_flags=_unique_preserve_order(quality_flags),
                    )
                )
        return sorted(scores, key=lambda item: (-item.match_confidence, item.claim_code))

    def _build_hit(
        self,
        evidence_record: Any,
        text: str,
        entities: ExtractedClaimEntities,
        score: "_ClaimMatchScore",
        review_for_close_match: bool,
    ) -> ClaimHitDraft:
        evidence_id = _evidence_id(evidence_record)
        source_sentence_key = _source_sentence_key(evidence_record)
        quality_flags = list(score.quality_flags)
        if review_for_close_match:
            quality_flags.append("multi_claim_close_match")
        review_required = review_for_close_match or score.match_confidence < Decimal("0.5500")
        hit_hash = _build_hit_hash(
            sku_code=_sku_code(evidence_record),
            claim_code=score.claim_code,
            hit_source_type=_hit_source_type(evidence_record),
            source_sentence_key=source_sentence_key,
            matched_keywords=score.matched_keywords,
            matched_param_codes=score.matched_param_codes,
            extracted_entity_json=entities.to_json(),
            match_method=score.match_method,
            match_confidence=score.match_confidence,
            quality_flags=quality_flags,
            promo_evidence_ids=[evidence_id] if evidence_id else [],
            seed_version=self.seed_version,
            rule_version=self.rule_version,
        )
        return ClaimHitDraft(
            claim_hit_id=_build_hit_id(
                project_id=self.project_id,
                batch_id=self.batch_id,
                sku_code=_sku_code(evidence_record),
                claim_code=score.claim_code,
                hit_source_type=_hit_source_type(evidence_record),
                source_sentence_key=source_sentence_key,
                rule_version=self.rule_version,
            ),
            project_id=self.project_id,
            category_code=self.category_code,
            batch_id=self.batch_id,
            run_id=self.run_id,
            module_run_id=self.module_run_id,
            sku_code=_sku_code(evidence_record),
            model_name=_model_name(evidence_record),
            claim_code=score.claim_code,
            claim_name=score.claim.claim_name,
            claim_group=str(score.claim.claim_group),
            hit_source_type=_hit_source_type(evidence_record),
            source_sentence_key=source_sentence_key,
            claim_seq=_int_or_none(_first_existing(_field_value(evidence_record, "claim_seq"), _payload(evidence_record).get("claim_seq"))),
            sentence_seq=_int_or_none(
                _first_existing(_field_value(evidence_record, "sentence_seq"), _payload(evidence_record).get("sentence_seq"))
            ),
            claim_fragment=_claim_fragment(text, score.matched_keywords),
            matched_keywords=score.matched_keywords,
            title_hint=_title_hint(evidence_record),
            extracted_entity_json=entities.to_json(),
            matched_param_codes=score.matched_param_codes,
            match_method=score.match_method,
            promo_evidence_ids=[evidence_id] if evidence_id else [],
            param_evidence_ids=[],
            quality_evidence_ids=[],
            match_confidence=score.match_confidence,
            quality_flags=_unique_preserve_order(quality_flags),
            review_required=review_required,
            review_status=(
                ClaimReviewStatus.REVIEW_REQUIRED.value if review_required else ClaimReviewStatus.AUTO_PASS.value
            ),
            hit_hash=hit_hash,
            seed_version=self.seed_version,
            rule_version=self.rule_version,
        )


@dataclass(frozen=True)
class _ClaimMatchScore:
    claim: StdClaimDefinition
    claim_code: str
    matched_keywords: list[str]
    matched_param_codes: list[str]
    match_method: str
    match_confidence: Decimal
    quality_flags: list[str]

    @property
    def confidence(self) -> Decimal:
        return self.match_confidence


def _close_review_codes(scores: list[_ClaimMatchScore]) -> set[str]:
    if len(scores) <= 1:
        return set()
    top_score = scores[0].match_confidence
    close_scores = [score for score in scores if top_score - score.match_confidence <= CLOSE_MATCH_DELTA]
    if len(close_scores) <= 1:
        return set()
    return {score.claim_code for score in close_scores}


def _extract_numeric_entities(text: str) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    patterns = [
        (r"(?P<raw>(?P<value>\d+(?:\.\d+)?)\s*(?:Hz|赫兹))", "Hz", "refresh_rate"),
        (r"(?P<raw>(?P<value>\d+(?:\.\d+)?)\s*(?:nits|尼特))", "nits", "brightness"),
        (r"(?P<raw>(?P<value>\d+(?:\.\d+)?)\s*(?:分区|级分区))", "zones", "dimming_zones"),
        (r"(?P<raw>(?P<value>\d+(?:\.\d+)?)\s*W)", "W", "speaker_power"),
        (r"(?P<raw>(?P<value>\d+(?:\.\d+)?)\s*(?:GB|G)(?:内存|运存)?)", "GB", "memory"),
        (r"(?P<raw>(?P<value>\d+(?:\.\d+)?)\s*ms)", "ms", "latency"),
        (r"(?P<raw>(?P<value>\d+(?:\.\d+)?)\s*(?:英寸|寸|inch))", "inch", "screen_size"),
        (r"(?P<raw>(?P<value>\d+(?:\.\d+)?)\s*声道)", "channel", "speaker_channel"),
    ]
    for pattern, unit, entity_type in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            value_text = match.group("value")
            raw = match.group("raw")
            entities.append(
                {
                    "raw": raw,
                    "value": _number_value(value_text),
                    "unit": unit,
                    "entity_type": entity_type,
                    "unit_uncertain": False,
                }
            )
    return _unique_entity_dicts(entities)


def _find_terms(text: str, terms: list[str]) -> list[str]:
    return _unique_preserve_order(term for term in terms if _contains_term(text, term))


def _matched_terms(text: str, terms: list[str]) -> list[str]:
    return _unique_preserve_order(term for term in terms if _contains_term(text, term))


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(_contains_term(text, term) for term in terms)


def _contains_term(text: str, term: str) -> bool:
    if not term:
        return False
    return term.casefold() in text.casefold()


def _has_required_claim_context(text: str, claim_code: str) -> bool:
    required_terms = SPECIFIC_CLAIM_REQUIRED_TERMS.get(claim_code)
    if not required_terms:
        return True
    return _contains_any(text, required_terms)


def _has_specific_entity(text: str) -> bool:
    specific_terms = [
        "Mini LED",
        "MiniLED",
        "OLED",
        "QLED",
        "HDR",
        "HDMI",
        "VRR",
        "ALLM",
        "Dolby",
        "杜比",
        "低蓝光",
        "无频闪",
        "安装",
    ]
    return _contains_any(text, specific_terms) or bool(_extract_numeric_entities(text))


def _build_hit_id(
    *,
    project_id: str,
    batch_id: str,
    sku_code: str,
    claim_code: str,
    hit_source_type: str,
    source_sentence_key: str,
    rule_version: str,
) -> str:
    digest = stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "sku_code": sku_code,
            "claim_code": claim_code,
            "hit_source_type": hit_source_type,
            "source_sentence_key": source_sentence_key,
            "rule_version": rule_version,
        },
        version=CLAIM_HIT_ID_HASH_VERSION,
    ).split(":")[-1]
    return f"m04ahit_{digest[:32]}"


def _build_hit_hash(**payload: Any) -> str:
    return stable_hash(payload, version=CLAIM_HIT_HASH_VERSION)


def _is_current_promo_evidence(record: Any) -> bool:
    evidence_type = _enum_value(_field_value(record, "evidence_type") or "")
    if evidence_type not in PROMO_EVIDENCE_TYPES:
        return False
    evidence_status = _field_value(record, "evidence_status")
    if evidence_status is not None and _enum_value(evidence_status) != Core3EvidenceStatus.CURRENT.value:
        return False
    if _field_value(record, "is_current") is False:
        return False
    return True


def _hit_source_type(record: Any) -> str:
    evidence_type = _enum_value(_field_value(record, "evidence_type") or "")
    if evidence_type == Core3EvidenceType.PROMO_RAW.value:
        return ClaimHitSourceType.PROMO_RAW.value
    return ClaimHitSourceType.PROMO_SENTENCE.value


def _promo_text(record: Any) -> str | None:
    payload = _payload(record)
    return _first_non_empty(
        _field_value(record, "text_value"),
        _field_value(record, "clean_value"),
        _field_value(record, "raw_value"),
        payload.get("sentence_text"),
        payload.get("clean_claim_text"),
        payload.get("raw_claim_text"),
    )


def _title_hint(record: Any) -> str | None:
    payload = _payload(record)
    value = _first_non_empty(
        _field_value(record, "title_hint"),
        payload.get("title_hint"),
        payload.get("sentence_role_hint"),
    )
    if value and _contains_any(value, TITLE_HINT_WORDS):
        return value
    return value


def _source_sentence_key(record: Any) -> str:
    payload = _payload(record)
    return _first_non_empty(
        _field_value(record, "evidence_key"),
        _field_value(record, "text_hash"),
        payload.get("sentence_text_hash"),
        _field_value(record, "evidence_id"),
    ) or ""


def _claim_fragment(text: str, matched_keywords: list[str]) -> str | None:
    if not matched_keywords:
        return text[:120] if text else None
    keyword = matched_keywords[0]
    index = text.casefold().find(keyword.casefold())
    if index < 0:
        return text[:120]
    start = max(index - 20, 0)
    end = min(index + len(keyword) + 40, len(text))
    return text[start:end]


def _sku_code(record: Any) -> str:
    return str(_field_value(record, "sku_code") or "")


def _model_name(record: Any) -> str | None:
    return _optional_string(_field_value(record, "model_name"))


def _evidence_id(record: Any) -> str | None:
    return _optional_string(_field_value(record, "evidence_id"))


def _payload(record: Any) -> dict[str, Any]:
    value = _field_value(record, "evidence_payload_json")
    return dict(value) if isinstance(value, Mapping) else {}


def _field_value(record: Any, field_name: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(field_name)
    if hasattr(record, "model_dump"):
        return record.model_dump().get(field_name)
    return getattr(record, field_name, None)


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _first_existing(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        text = _optional_string(value)
        if text:
            return text
    return None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _number_value(value: str) -> int | float:
    number = float(value)
    return int(number) if number.is_integer() else number


def _unique_preserve_order(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def _unique_entity_dicts(values: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for value in values:
        key = (value.get("raw"), value.get("unit"), value.get("entity_type"))
        if key in seen:
            continue
        result.append(value)
        seen.add(key)
    return result
