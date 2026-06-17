"""Seed loader for M06 comment downstream signals."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.core3_real_data.comment_downstream_signal_schemas import (
    M06SignalSeedBundle,
    SignalTargetDefinition,
)
from app.services.core3_real_data.constants import (
    CORE3_M06_SEED_VERSION,
    CommentSignalType,
)
from app.services.core3_real_data.hash_utils import stable_hash


DEFAULT_COMMENT_SIGNAL_SEED_PATH = (
    Path(__file__).resolve().parents[2] / "rules" / "tv_core3_mvp_seed_v0_2.json"
)

REQUIRED_SEED_SECTIONS = (
    "standard_claims",
    "user_tasks",
    "target_groups",
    "battlefields",
    "comment_topics",
)


class CommentSignalSeedValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass(frozen=True)
class CommentSignalSeedLoadResult:
    seed: M06SignalSeedBundle
    seed_path: Path
    seed_version: str
    asset_version: str
    seed_content_hash: str
    target_counts: dict[str, int]


class CommentSignalSeedLoader:
    """Load all dictionaries M06 needs without hard-coding business targets."""

    def __init__(self, seed_path: Path | str | None = None) -> None:
        self.seed_path = Path(seed_path) if seed_path is not None else DEFAULT_COMMENT_SIGNAL_SEED_PATH

    def load(self) -> CommentSignalSeedLoadResult:
        raw_seed = self._load_raw_seed()
        errors = self._validate_sections(raw_seed)
        if errors:
            raise CommentSignalSeedValidationError(errors)

        raw_version = str(raw_seed.get("version") or CORE3_M06_SEED_VERSION)
        targets: dict[CommentSignalType, list[SignalTargetDefinition]] = {
            CommentSignalType.CLAIM_VALIDATION: self._claim_targets(raw_seed["standard_claims"]),
            CommentSignalType.TASK_CUE: self._task_targets(raw_seed["user_tasks"]),
            CommentSignalType.TARGET_GROUP_CUE: self._group_targets(raw_seed["target_groups"]),
            CommentSignalType.BATTLEFIELD_SUPPORT: self._battlefield_targets(raw_seed["battlefields"]),
            CommentSignalType.PAIN_POINT: self._risk_targets(),
            CommentSignalType.PRICE_PERCEPTION: self._price_targets(),
            CommentSignalType.SERVICE_SIGNAL: self._service_targets(),
        }
        topic_to_claim_codes: dict[str, list[str]] = {}
        topic_to_task_codes: dict[str, list[str]] = {}
        topic_to_battlefield_codes: dict[str, list[str]] = {}
        topic_to_service_guardrail: dict[str, bool] = {}
        for topic in raw_seed["comment_topics"]:
            topic_code = str(topic.get("topic_code") or "")
            if not topic_code:
                continue
            topic_to_claim_codes[topic_code] = _strings(topic.get("mapped_claim_codes"))
            topic_to_task_codes[topic_code] = _strings(topic.get("mapped_task_codes"))
            topic_to_battlefield_codes[topic_code] = _strings(topic.get("mapped_battlefield_codes"))
            topic_to_service_guardrail[topic_code] = bool(topic.get("service_guardrail"))

        seed_content_hash = stable_hash(
            {
                "targets": {
                    signal_type.value: [target.model_dump(mode="json") for target in signal_targets]
                    for signal_type, signal_targets in targets.items()
                },
                "topic_to_claim_codes": topic_to_claim_codes,
                "topic_to_task_codes": topic_to_task_codes,
                "topic_to_battlefield_codes": topic_to_battlefield_codes,
                "topic_to_service_guardrail": topic_to_service_guardrail,
            },
            version="m06_comment_signal_seed_v1",
        )
        seed = M06SignalSeedBundle(
            seed_version=CORE3_M06_SEED_VERSION,
            asset_version=raw_version,
            seed_content_hash=seed_content_hash,
            targets=targets,
            topic_to_claim_codes=topic_to_claim_codes,
            topic_to_task_codes=topic_to_task_codes,
            topic_to_battlefield_codes=topic_to_battlefield_codes,
            topic_to_service_guardrail=topic_to_service_guardrail,
        )
        return CommentSignalSeedLoadResult(
            seed=seed,
            seed_path=self.seed_path,
            seed_version=CORE3_M06_SEED_VERSION,
            asset_version=raw_version,
            seed_content_hash=seed_content_hash,
            target_counts={signal_type.value: len(items) for signal_type, items in targets.items()},
        )

    def _load_raw_seed(self) -> dict[str, Any]:
        try:
            return json.loads(self.seed_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise CommentSignalSeedValidationError([f"seed file not found: {self.seed_path}"]) from exc
        except json.JSONDecodeError as exc:
            raise CommentSignalSeedValidationError([f"seed file is not valid JSON: {exc.msg}"]) from exc

    @staticmethod
    def _validate_sections(raw_seed: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for section in REQUIRED_SEED_SECTIONS:
            if not isinstance(raw_seed.get(section), list) or not raw_seed.get(section):
                errors.append(f"{section} must be a non-empty list")
        return errors

    @staticmethod
    def _claim_targets(raw_claims: list[dict[str, Any]]) -> list[SignalTargetDefinition]:
        return [
            SignalTargetDefinition(
                signal_type=CommentSignalType.CLAIM_VALIDATION,
                code=str(item["claim_code"]),
                name=str(item["claim_name"]),
                group_hint=str(item.get("claim_group") or ""),
                keywords=_strings(item.get("keywords")) + _strings(item.get("promo_keywords")),
                aliases=_strings(item.get("aliases")),
                topic_codes=_strings(item.get("comment_topic_codes")),
                mapped_task_codes=_strings(item.get("mapped_task_codes")),
                mapped_battlefield_codes=_strings(item.get("mapped_battlefield_codes")),
                metadata_json={"source": "standard_claims", "evidence_requirement": item.get("evidence_requirement", [])},
            )
            for item in raw_claims
            if item.get("claim_code") and item.get("claim_name")
        ]

    @staticmethod
    def _task_targets(raw_tasks: list[dict[str, Any]]) -> list[SignalTargetDefinition]:
        return [
            SignalTargetDefinition(
                signal_type=CommentSignalType.TASK_CUE,
                code=str(item["task_code"]),
                name=str(item["task_name"]),
                group_hint="user_task",
                keywords=_strings(item.get("keywords")),
                aliases=_strings(item.get("aliases")),
                topic_codes=_strings(item.get("comment_topic_codes")) + _strings(item.get("mapped_topic_codes")),
                mapped_claim_codes=_strings(item.get("mapped_claim_codes")) + _strings(item.get("positive_claim_codes")),
                mapped_battlefield_codes=_strings(item.get("mapped_battlefield_codes")) + _strings(item.get("battlefield_codes")),
                metadata_json={
                    "source": "user_tasks",
                    "default_target_group_codes": _strings(item.get("default_target_group_codes")),
                },
            )
            for item in raw_tasks
            if item.get("task_code") and item.get("task_name")
        ]

    @staticmethod
    def _group_targets(raw_groups: list[dict[str, Any]]) -> list[SignalTargetDefinition]:
        return [
            SignalTargetDefinition(
                signal_type=CommentSignalType.TARGET_GROUP_CUE,
                code=str(item["target_group_code"]),
                name=str(item["target_group_name"]),
                group_hint="target_group",
                keywords=_strings(item.get("keywords")),
                aliases=_strings(item.get("aliases")),
                mapped_task_codes=_strings(item.get("mapped_task_codes")) + _strings(item.get("source_task_codes")),
                mapped_battlefield_codes=_strings(item.get("mapped_battlefield_codes")),
                metadata_json={"source": "target_groups"},
            )
            for item in raw_groups
            if item.get("target_group_code") and item.get("target_group_name")
        ]

    @staticmethod
    def _battlefield_targets(raw_battlefields: list[dict[str, Any]]) -> list[SignalTargetDefinition]:
        return [
            SignalTargetDefinition(
                signal_type=CommentSignalType.BATTLEFIELD_SUPPORT,
                code=str(item["battlefield_code"]),
                name=str(item["battlefield_name"]),
                group_hint="battlefield",
                keywords=_strings(item.get("keywords")),
                aliases=_strings(item.get("aliases")),
                topic_codes=_strings(item.get("comment_topic_codes")) + _strings(item.get("mapped_topic_codes")),
                mapped_claim_codes=_strings(item.get("mapped_claim_codes")) + _strings(item.get("core_claim_codes")),
                mapped_task_codes=_strings(item.get("mapped_task_codes")) + _strings(item.get("core_task_codes")),
                metadata_json={"source": "battlefields", "entry_thresholds": item.get("entry_thresholds", {})},
            )
            for item in raw_battlefields
            if item.get("battlefield_code") and item.get("battlefield_name")
        ]

    @staticmethod
    def _risk_targets() -> list[SignalTargetDefinition]:
        definitions = {
            "RISK_PICTURE_NEGATIVE": ("画质负向", ["模糊", "偏色", "不清楚", "反光", "画质差"]),
            "RISK_MOTION_LAG": ("运动拖影卡顿", ["拖影", "卡顿", "看球不顺", "掉帧", "延迟"]),
            "RISK_SYSTEM_ADS_LAG": ("系统广告和卡顿", ["广告", "弹窗", "系统卡", "复杂"]),
            "RISK_AUDIO_NEGATIVE": ("音质负向", ["声音小", "破音", "低音差", "音质差"]),
            "RISK_EYE_DISCOMFORT": ("护眼不适", ["刺眼", "累眼", "看久不舒服"]),
            "RISK_SERVICE_DELIVERY": ("服务配送风险", ["配送慢", "安装差", "客服差", "售后差"]),
            "RISK_DURABILITY_QUALITY": ("做工耐用风险", ["故障", "坏点", "品控差", "做工差"]),
            "RISK_PRICE_OVERPAY": ("价格不值风险", ["太贵", "不值", "降价", "背刺"]),
        }
        return [
            SignalTargetDefinition(
                signal_type=CommentSignalType.PAIN_POINT,
                code=code,
                name=name,
                group_hint="risk",
                keywords=keywords,
                metadata_json={"source": "builtin_risk"},
            )
            for code, (name, keywords) in definitions.items()
        ]

    @staticmethod
    def _price_targets() -> list[SignalTargetDefinition]:
        definitions = {
            "PRICE_VALUE_POSITIVE": ("价值正向", ["性价比", "划算", "值得", "值", "买得值"]),
            "PRICE_VALUE_NEGATIVE": ("价值负向", ["太贵", "不值", "价格高", "后悔"]),
            "PRICE_PROMOTION_SENSITIVE": ("促销敏感", ["活动", "优惠", "补贴", "赠品"]),
            "PRICE_BIG_SCREEN_VALUE": ("大屏价格价值", ["大屏", "85", "这个价", "划算"]),
            "PRICE_DROP_RISK": ("降价风险", ["降价", "背刺", "保价"]),
        }
        return [
            SignalTargetDefinition(
                signal_type=CommentSignalType.PRICE_PERCEPTION,
                code=code,
                name=name,
                group_hint="price_perception",
                keywords=keywords,
                metadata_json={"source": "builtin_price"},
            )
            for code, (name, keywords) in definitions.items()
        ]

    @staticmethod
    def _service_targets() -> list[SignalTargetDefinition]:
        definitions = {
            "SERVICE_INSTALL_POSITIVE": ("安装正向", ["安装快", "师傅专业", "挂装好", "安装很好"]),
            "SERVICE_DELIVERY_POSITIVE": ("配送正向", ["送货快", "物流好", "包装好"]),
            "SERVICE_SUPPORT_POSITIVE": ("客服售后正向", ["客服好", "售后响应", "售后好"]),
            "SERVICE_INSTALL_NEGATIVE": ("安装负向", ["安装慢", "不专业", "收费不清", "安装差"]),
            "SERVICE_DELIVERY_NEGATIVE": ("配送负向", ["配送慢", "破损", "送错"]),
            "SERVICE_SUPPORT_NEGATIVE": ("客服售后负向", ["售后差", "客服差", "不处理"]),
        }
        return [
            SignalTargetDefinition(
                signal_type=CommentSignalType.SERVICE_SIGNAL,
                code=code,
                name=name,
                group_hint="service",
                keywords=keywords,
                metadata_json={"source": "builtin_service"},
            )
            for code, (name, keywords) in definitions.items()
        ]


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result
