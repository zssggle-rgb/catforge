"""Seed loader for M05 comment topic definitions."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.services.core3_real_data.comment_evidence_schemas import (
    CommentTopicSeed,
    CommentTopicSeedIndex,
)
from app.services.core3_real_data.constants import (
    CORE3_M05_SEED_VERSION,
    CommentDomainHint,
    Core3CategoryCode,
)
from app.services.core3_real_data.hash_utils import stable_hash


DEFAULT_COMMENT_TOPIC_SEED_PATH = (
    Path(__file__).resolve().parents[2] / "rules" / "tv_core3_mvp_seed_v0_2.json"
)

REQUIRED_COMMENT_TOPIC_FIELDS = (
    "topic_code",
    "topic_name",
    "definition",
    "topic_group",
    "aliases",
    "keywords",
    "positive_keywords",
    "negative_keywords",
    "source_types",
    "evidence_requirement",
    "mapped_claim_codes",
    "mapped_task_codes",
    "mapped_battlefield_codes",
    "activates_product_claim",
)

REQUIRED_COMMENT_TOPIC_CODES = frozenset(
    {
        "TOPIC_PICTURE_QUALITY",
        "TOPIC_BRIGHTNESS_HDR",
        "TOPIC_DARK_SCENE_CONTRAST",
        "TOPIC_SPORTS_WATCHING",
        "TOPIC_GAMING_SMOOTHNESS",
        "TOPIC_EYE_COMFORT",
        "TOPIC_EASE_OF_USE",
        "TOPIC_SENIOR_FRIENDLY",
        "TOPIC_CHILD_FAMILY",
        "TOPIC_INTERFACE_CONNECTIVITY",
        "TOPIC_AUDIO_QUALITY",
        "TOPIC_SYSTEM_ADS_PERFORMANCE",
        "TOPIC_SIZE_SPACE_FIT",
        "TOPIC_PRICE_VALUE",
        "TOPIC_INSTALLATION_SERVICE",
        "TOPIC_DURABILITY_QUALITY",
    }
)

SUPPORTED_COMMENT_TOPIC_GROUPS = frozenset(
    {
        CommentDomainHint.PRODUCT_EXPERIENCE.value,
        CommentDomainHint.PRODUCT_RISK.value,
        CommentDomainHint.MARKET_PERCEPTION.value,
        CommentDomainHint.SERVICE_EXPERIENCE.value,
        CommentDomainHint.LOGISTICS_INSTALLATION.value,
    }
)

M05_USABLE_SOURCE_TYPES = frozenset({"comment_text"})
IGNORED_SOURCE_TYPES = frozenset({"market_fact"})
COMMENT_TOPIC_SEED_HASH_VERSION = "m05_comment_topic_seed_v1"


class CommentTopicSeedValidationError(ValueError):
    """Raised when the TV M05 comment topic seed violates the required contract."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass(frozen=True)
class CommentTopicSeedLoadResult:
    seed: CommentTopicSeedIndex
    seed_path: Path
    seed_version: str
    asset_version: str | None
    raw_version: str | None
    seed_content_hash: str
    comment_topic_count: int
    required_topic_codes: list[str]
    topic_group_counts: dict[str, int]
    keyword_index: dict[str, list[str]]
    positive_keyword_index: dict[str, list[str]]
    negative_keyword_index: dict[str, list[str]]
    alias_index: dict[str, list[str]]
    dimension_path_index: dict[str, list[str]]
    ignored_source_type_counts: dict[str, int]
    product_claim_topic_codes: list[str]
    service_guardrail_topic_codes: list[str]


class CommentTopicSeedLoader:
    """Load and normalize the TV core3 M05 comment topic seed."""

    def __init__(self, seed_path: Path | str | None = None) -> None:
        self.seed_path = Path(seed_path) if seed_path is not None else DEFAULT_COMMENT_TOPIC_SEED_PATH

    def load(self) -> CommentTopicSeedLoadResult:
        raw_seed = self._load_raw_seed()
        raw_topics = raw_seed.get("comment_topics")
        errors: list[str] = []

        if not isinstance(raw_topics, list) or not raw_topics:
            raise CommentTopicSeedValidationError(["comment_topics must be a non-empty list"])

        errors.extend(self._validate_unique_topic_codes(raw_topics))

        topics: list[CommentTopicSeed] = []
        ignored_source_type_counts: Counter[str] = Counter()
        for index, raw_topic in enumerate(raw_topics):
            try:
                topic, ignored_source_types = self._normalize_topic(raw_topic, index)
            except CommentTopicSeedValidationError as exc:
                errors.extend(exc.errors)
                continue
            topics.append(topic)
            ignored_source_type_counts.update(ignored_source_types)

        loaded_topic_codes = {topic.topic_code for topic in topics}
        missing_topic_codes = sorted(REQUIRED_COMMENT_TOPIC_CODES - loaded_topic_codes)
        if missing_topic_codes:
            errors.append(f"comment_topics missing required topic codes: {', '.join(missing_topic_codes)}")

        if errors:
            raise CommentTopicSeedValidationError(errors)

        raw_version = self._optional_string(raw_seed.get("version"))
        topic_group_counts = Counter(topic.topic_group for topic in topics)
        keyword_index = self._build_index(topics, "keywords")
        positive_keyword_index = self._build_index(topics, "positive_keywords")
        negative_keyword_index = self._build_index(topics, "negative_keywords")
        alias_index = self._build_index(topics, "aliases")
        dimension_path_index = self._build_index(topics, "dimension_paths")
        product_claim_topic_codes = sorted(
            topic.topic_code for topic in topics if topic.activates_product_claim
        )
        service_guardrail_topic_codes = sorted(
            topic.topic_code for topic in topics if topic.service_guardrail
        )
        seed_content_hash = stable_hash(
            [topic.model_dump() for topic in topics],
            version=COMMENT_TOPIC_SEED_HASH_VERSION,
        )

        seed = CommentTopicSeedIndex(
            seed_version=CORE3_M05_SEED_VERSION,
            category_code=Core3CategoryCode.TV,
            topics=topics,
            metadata_json={
                "asset_version": raw_version,
                "raw_seed_version": raw_version,
                "source_seed_file": self.seed_path.name,
                "seed_content_hash": seed_content_hash,
                "raw_comment_topic_count": len(raw_topics),
                "required_comment_topic_count": len(REQUIRED_COMMENT_TOPIC_CODES),
                "required_topic_codes": sorted(REQUIRED_COMMENT_TOPIC_CODES),
                "extra_topic_codes": sorted(loaded_topic_codes - REQUIRED_COMMENT_TOPIC_CODES),
                "topic_group_counts": dict(sorted(topic_group_counts.items())),
                "keyword_index": keyword_index,
                "positive_keyword_index": positive_keyword_index,
                "negative_keyword_index": negative_keyword_index,
                "alias_index": alias_index,
                "dimension_path_index": dimension_path_index,
                "ignored_source_type_counts": dict(sorted(ignored_source_type_counts.items())),
                "m05_usable_source_types": sorted(M05_USABLE_SOURCE_TYPES),
                "ignored_source_types": sorted(IGNORED_SOURCE_TYPES),
                "product_claim_topic_codes": product_claim_topic_codes,
                "service_guardrail_topic_codes": service_guardrail_topic_codes,
            },
        )
        return CommentTopicSeedLoadResult(
            seed=seed,
            seed_path=self.seed_path,
            seed_version=CORE3_M05_SEED_VERSION,
            asset_version=raw_version,
            raw_version=raw_version,
            seed_content_hash=seed_content_hash,
            comment_topic_count=len(topics),
            required_topic_codes=sorted(REQUIRED_COMMENT_TOPIC_CODES),
            topic_group_counts=dict(sorted(topic_group_counts.items())),
            keyword_index=keyword_index,
            positive_keyword_index=positive_keyword_index,
            negative_keyword_index=negative_keyword_index,
            alias_index=alias_index,
            dimension_path_index=dimension_path_index,
            ignored_source_type_counts=dict(sorted(ignored_source_type_counts.items())),
            product_claim_topic_codes=product_claim_topic_codes,
            service_guardrail_topic_codes=service_guardrail_topic_codes,
        )

    def load_seed(self) -> CommentTopicSeedIndex:
        return self.load().seed

    def _load_raw_seed(self) -> dict[str, Any]:
        try:
            raw_seed = json.loads(self.seed_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise CommentTopicSeedValidationError([f"seed file not found: {self.seed_path}"]) from exc
        except json.JSONDecodeError as exc:
            raise CommentTopicSeedValidationError([f"seed file is not valid JSON: {exc.msg}"]) from exc

        if not isinstance(raw_seed, dict):
            raise CommentTopicSeedValidationError(["seed root must be a JSON object"])
        return raw_seed

    def _normalize_topic(self, raw_topic: Any, index: int) -> tuple[CommentTopicSeed, list[str]]:
        prefix = f"comment_topics[{index}]"
        errors: list[str] = []
        if not isinstance(raw_topic, dict):
            raise CommentTopicSeedValidationError([f"{prefix} must be an object"])

        for field_name in REQUIRED_COMMENT_TOPIC_FIELDS:
            value = raw_topic.get(field_name)
            if value is None or value == "":
                errors.append(f"{prefix}.{field_name} is required")

        if errors:
            raise CommentTopicSeedValidationError(errors)

        topic_code = str(raw_topic["topic_code"]).strip()
        topic_group = self._normalize_topic_group(str(raw_topic["topic_group"]), prefix)
        source_types, ignored_source_types = self._normalize_source_types(raw_topic["source_types"], prefix)
        activates_product_claim = self._normalize_bool(
            raw_topic["activates_product_claim"],
            f"{prefix}.activates_product_claim",
        )

        try:
            topic = CommentTopicSeed(
                topic_code=topic_code,
                topic_name=str(raw_topic["topic_name"]).strip(),
                topic_group=topic_group,
                topic_definition=self._optional_string(raw_topic.get("definition")),
                aliases=self._normalize_string_list(raw_topic["aliases"], f"{prefix}.aliases", required=True),
                keywords=self._normalize_string_list(raw_topic["keywords"], f"{prefix}.keywords", required=True),
                positive_keywords=self._normalize_string_list(
                    raw_topic["positive_keywords"],
                    f"{prefix}.positive_keywords",
                ),
                negative_keywords=self._normalize_string_list(
                    raw_topic["negative_keywords"],
                    f"{prefix}.negative_keywords",
                ),
                source_types=source_types,
                evidence_requirement=self._normalize_string_list(
                    raw_topic["evidence_requirement"],
                    f"{prefix}.evidence_requirement",
                    required=True,
                ),
                dimension_paths=self._normalize_string_list(
                    raw_topic.get("dimension_paths", []),
                    f"{prefix}.dimension_paths",
                ),
                mapped_claim_codes=self._normalize_string_list(
                    raw_topic["mapped_claim_codes"],
                    f"{prefix}.mapped_claim_codes",
                ),
                mapped_task_codes=self._normalize_string_list(
                    raw_topic["mapped_task_codes"],
                    f"{prefix}.mapped_task_codes",
                ),
                mapped_battlefield_codes=self._normalize_string_list(
                    raw_topic["mapped_battlefield_codes"],
                    f"{prefix}.mapped_battlefield_codes",
                ),
                activates_product_claim=activates_product_claim,
                service_guardrail=topic_group == CommentDomainHint.SERVICE_EXPERIENCE.value,
                priority=index,
            )
        except ValidationError as exc:
            raise CommentTopicSeedValidationError([f"{prefix}: {exc}"]) from exc

        return topic, ignored_source_types

    def _validate_unique_topic_codes(self, raw_topics: list[Any]) -> list[str]:
        topic_codes: list[str] = []
        for raw_topic in raw_topics:
            if isinstance(raw_topic, dict) and raw_topic.get("topic_code") is not None:
                topic_codes.append(str(raw_topic["topic_code"]).strip())

        duplicates = sorted(code for code, count in Counter(topic_codes).items() if code and count > 1)
        if duplicates:
            return [f"topic_code must be unique in comment_topics: {', '.join(duplicates)}"]
        return []

    def _normalize_topic_group(self, raw_topic_group: str, prefix: str) -> str:
        topic_group = raw_topic_group.strip()
        if topic_group not in SUPPORTED_COMMENT_TOPIC_GROUPS:
            raise CommentTopicSeedValidationError([f"{prefix}.topic_group is unsupported: {topic_group}"])
        return topic_group

    def _normalize_source_types(self, raw_source_types: Any, prefix: str) -> tuple[list[str], list[str]]:
        if not isinstance(raw_source_types, list):
            raise CommentTopicSeedValidationError([f"{prefix}.source_types must be a list"])

        source_types: list[str] = []
        ignored_source_types: list[str] = []
        seen_sources: set[str] = set()
        errors: list[str] = []
        for raw_source_type in raw_source_types:
            source_type = str(raw_source_type).strip()
            if source_type in IGNORED_SOURCE_TYPES:
                ignored_source_types.append(source_type)
                continue
            if source_type not in M05_USABLE_SOURCE_TYPES:
                errors.append(f"{prefix}.source_types has unsupported source type: {source_type}")
                continue
            if source_type not in seen_sources:
                source_types.append(source_type)
                seen_sources.add(source_type)

        if errors:
            raise CommentTopicSeedValidationError(errors)
        if not source_types:
            raise CommentTopicSeedValidationError([f"{prefix}.source_types has no M05-usable source type"])
        return source_types, ignored_source_types

    def _normalize_bool(self, raw_value: Any, field_path: str) -> bool:
        if isinstance(raw_value, bool):
            return raw_value
        raise CommentTopicSeedValidationError([f"{field_path} must be a boolean"])

    def _normalize_string_list(
        self,
        raw_values: Any,
        field_path: str,
        *,
        required: bool = False,
    ) -> list[str]:
        if raw_values is None:
            raw_values = []
        if not isinstance(raw_values, list):
            raise CommentTopicSeedValidationError([f"{field_path} must be a list"])
        values = [str(value).strip() for value in raw_values if str(value).strip()]
        if required and not values:
            raise CommentTopicSeedValidationError([f"{field_path} must not be empty"])
        return values

    def _optional_string(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _build_index(self, topics: list[CommentTopicSeed], field_name: str) -> dict[str, list[str]]:
        index: dict[str, set[str]] = {}
        for topic in topics:
            values = getattr(topic, field_name)
            for raw_value in values:
                value = str(raw_value).strip()
                if not value:
                    continue
                index.setdefault(value, set()).add(topic.topic_code)
        return {key: sorted(topic_codes) for key, topic_codes in sorted(index.items())}
