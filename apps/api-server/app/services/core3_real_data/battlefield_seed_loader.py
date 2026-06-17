"""Read and validate the TV battlefield seed used by M11."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.services.core3_real_data.constants import (
    CORE3_M09_EXPECTED_TASK_CODES,
    CORE3_M10_EXPECTED_TARGET_GROUP_CODES,
    CORE3_M11_EXPECTED_BATTLEFIELD_CODES,
    CORE3_M11_SEED_VERSION,
)
from app.services.core3_real_data.hash_utils import stable_hash


SEED_FILE_NAME = "tv_core3_mvp_seed_v0_2.json"


class M11BattlefieldSeedError(RuntimeError):
    pass


@dataclass(frozen=True)
class M11BattlefieldSeed:
    seed_version: str
    file_version: str
    seed_hash: str
    raw_seed: dict[str, Any]
    battlefields: tuple[dict[str, Any], ...]
    target_groups_by_battlefield: dict[str, tuple[str, ...]]

    @property
    def battlefield_count(self) -> int:
        return len(self.battlefields)


class M11BattlefieldSeedLoader:
    def __init__(self, seed_path: Path | None = None) -> None:
        self.seed_path = seed_path or Path(__file__).parents[2] / "rules" / SEED_FILE_NAME

    def load(self) -> M11BattlefieldSeed:
        if not self.seed_path.exists():
            raise M11BattlefieldSeedError(f"M11 价值战场 seed 不存在：{self.seed_path}")
        raw_seed = json.loads(self.seed_path.read_text(encoding="utf-8"))
        self._validate_seed(raw_seed)
        battlefields = tuple(dict(item) for item in raw_seed["battlefields"])
        return M11BattlefieldSeed(
            seed_version=CORE3_M11_SEED_VERSION,
            file_version=str(raw_seed["version"]),
            seed_hash=stable_hash(
                {
                    "battlefields": battlefields,
                    "target_group_links": raw_seed.get("target_groups") or [],
                },
                version="m11_battlefield_seed_hash_v1",
            ),
            raw_seed=raw_seed,
            battlefields=battlefields,
            target_groups_by_battlefield=self._target_groups_by_battlefield(raw_seed),
        )

    def _validate_seed(self, raw_seed: Mapping[str, Any]) -> None:
        if raw_seed.get("category_code") != "TV":
            raise M11BattlefieldSeedError("M11 价值战场 seed category_code 必须为 TV。")
        if not raw_seed.get("version"):
            raise M11BattlefieldSeedError("M11 价值战场 seed 缺少 version。")
        battlefields = list(raw_seed.get("battlefields") or [])
        expected_codes = tuple(CORE3_M11_EXPECTED_BATTLEFIELD_CODES)
        actual_codes = tuple(item.get("battlefield_code") for item in battlefields)
        if actual_codes != expected_codes:
            raise M11BattlefieldSeedError("M11 价值战场 seed 必须按 MVP 顺序覆盖 10 个固定战场。")
        if len(set(actual_codes)) != len(actual_codes):
            raise M11BattlefieldSeedError("M11 价值战场 seed 存在重复 battlefield_code。")
        for battlefield in battlefields:
            self._validate_battlefield(battlefield, raw_seed)
        self._validate_target_group_links(raw_seed)

    def _validate_battlefield(self, battlefield: Mapping[str, Any], raw_seed: Mapping[str, Any]) -> None:
        battlefield_code = str(battlefield.get("battlefield_code") or "")
        if not battlefield_code:
            raise M11BattlefieldSeedError("M11 价值战场 seed 存在空 battlefield_code。")
        if not battlefield.get("battlefield_name"):
            raise M11BattlefieldSeedError(f"{battlefield_code} 缺少中文战场名称。")
        if not battlefield.get("definition"):
            raise M11BattlefieldSeedError(f"{battlefield_code} 缺少战场定义。")
        source_task_codes = tuple(str(code) for code in battlefield.get("core_task_codes") or battlefield.get("mapped_task_codes") or ())
        if not source_task_codes and battlefield_code != "BF_SERVICE_ASSURANCE":
            raise M11BattlefieldSeedError(f"{battlefield_code} 缺少 core_task_codes，不能进入 M11。")
        unknown_tasks = sorted(set(source_task_codes) - set(CORE3_M09_EXPECTED_TASK_CODES))
        if unknown_tasks:
            raise M11BattlefieldSeedError(f"{battlefield_code} 引用了未知用户任务：{', '.join(unknown_tasks)}。")
        mapped_claim_codes = tuple(str(code) for code in battlefield.get("core_claim_codes") or battlefield.get("mapped_claim_codes") or ())
        known_claims = {
            str(item.get("claim_code"))
            for item in raw_seed.get("standard_claims") or []
            if item.get("claim_code")
        }
        unknown_claims = sorted(set(mapped_claim_codes) - known_claims)
        if unknown_claims:
            raise M11BattlefieldSeedError(f"{battlefield_code} 引用了未知标准卖点：{', '.join(unknown_claims)}。")
        if not battlefield.get("comment_topic_codes") and not battlefield.get("keywords"):
            raise M11BattlefieldSeedError(f"{battlefield_code} 缺少评论主题或关键词。")
        weights = dict(battlefield.get("semantic_market_weights") or {})
        if "semantic" not in weights or "market" not in weights:
            raise M11BattlefieldSeedError(f"{battlefield_code} 缺少 semantic_market_weights。")

    def _validate_target_group_links(self, raw_seed: Mapping[str, Any]) -> None:
        groups = list(raw_seed.get("target_groups") or [])
        actual_group_codes = tuple(item.get("target_group_code") for item in groups)
        if actual_group_codes != tuple(CORE3_M10_EXPECTED_TARGET_GROUP_CODES):
            raise M11BattlefieldSeedError("M11 seed 中 target_groups 必须与 M10 固定客群一致。")
        expected_battlefields = set(CORE3_M11_EXPECTED_BATTLEFIELD_CODES)
        for group in groups:
            group_code = str(group.get("target_group_code") or "")
            mapped = set(str(code) for code in group.get("mapped_battlefield_codes") or [])
            unknown = sorted(mapped - expected_battlefields)
            if unknown:
                raise M11BattlefieldSeedError(f"{group_code} 引用了未知价值战场：{', '.join(unknown)}。")

    @staticmethod
    def _target_groups_by_battlefield(raw_seed: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
        result: dict[str, list[str]] = {code: [] for code in CORE3_M11_EXPECTED_BATTLEFIELD_CODES}
        for group in raw_seed.get("target_groups") or []:
            group_code = str(group.get("target_group_code") or "")
            for battlefield_code in group.get("mapped_battlefield_codes") or []:
                code = str(battlefield_code)
                if code in result and group_code:
                    result[code].append(group_code)
        return {code: tuple(values) for code, values in result.items()}
