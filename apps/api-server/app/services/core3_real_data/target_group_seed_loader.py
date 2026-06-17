"""Read and validate the TV target-group seed used by M10."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.services.core3_real_data.constants import (
    CORE3_M09_EXPECTED_TASK_CODES,
    CORE3_M10_EXPECTED_TARGET_GROUP_CODES,
    CORE3_M10_SEED_VERSION,
)
from app.services.core3_real_data.hash_utils import stable_hash


SEED_FILE_NAME = "tv_core3_mvp_seed_v0_2.json"


class M10TargetGroupSeedError(RuntimeError):
    pass


@dataclass(frozen=True)
class M10TargetGroupSeed:
    seed_version: str
    file_version: str
    seed_hash: str
    raw_seed: dict[str, Any]
    target_groups: tuple[dict[str, Any], ...]

    @property
    def target_group_count(self) -> int:
        return len(self.target_groups)


class M10TargetGroupSeedLoader:
    def __init__(self, seed_path: Path | None = None) -> None:
        self.seed_path = seed_path or Path(__file__).parents[2] / "rules" / SEED_FILE_NAME

    def load(self) -> M10TargetGroupSeed:
        if not self.seed_path.exists():
            raise M10TargetGroupSeedError(f"M10 目标客群 seed 不存在：{self.seed_path}")
        raw_seed = json.loads(self.seed_path.read_text(encoding="utf-8"))
        self._validate_seed(raw_seed)
        target_groups = tuple(dict(item) for item in raw_seed["target_groups"])
        return M10TargetGroupSeed(
            seed_version=CORE3_M10_SEED_VERSION,
            file_version=str(raw_seed["version"]),
            seed_hash=stable_hash(target_groups, version="m10_target_group_seed_hash_v1"),
            raw_seed=raw_seed,
            target_groups=target_groups,
        )

    def _validate_seed(self, raw_seed: Mapping[str, Any]) -> None:
        if raw_seed.get("category_code") != "TV":
            raise M10TargetGroupSeedError("M10 目标客群 seed category_code 必须为 TV。")
        if not raw_seed.get("version"):
            raise M10TargetGroupSeedError("M10 目标客群 seed 缺少 version。")
        groups = list(raw_seed.get("target_groups") or [])
        expected_codes = tuple(CORE3_M10_EXPECTED_TARGET_GROUP_CODES)
        actual_codes = tuple(item.get("target_group_code") for item in groups)
        if actual_codes != expected_codes:
            raise M10TargetGroupSeedError("M10 目标客群 seed 必须按 MVP 顺序覆盖 9 个固定客群。")
        if len(set(actual_codes)) != len(actual_codes):
            raise M10TargetGroupSeedError("M10 目标客群 seed 存在重复 target_group_code。")
        for group in groups:
            self._validate_group(group)

    def _validate_group(self, group: Mapping[str, Any]) -> None:
        group_code = str(group.get("target_group_code") or "")
        if not group_code:
            raise M10TargetGroupSeedError("M10 目标客群 seed 存在空 target_group_code。")
        if not group.get("target_group_name"):
            raise M10TargetGroupSeedError(f"{group_code} 缺少中文客群名称。")
        if not group.get("definition"):
            raise M10TargetGroupSeedError(f"{group_code} 缺少客群定义。")
        source_task_codes = tuple(str(code) for code in group.get("source_task_codes") or group.get("mapped_task_codes") or ())
        if not source_task_codes:
            raise M10TargetGroupSeedError(f"{group_code} 缺少 source_task_codes，不能进入 M10。")
        unknown_tasks = sorted(set(source_task_codes) - set(CORE3_M09_EXPECTED_TASK_CODES))
        if unknown_tasks:
            raise M10TargetGroupSeedError(f"{group_code} 引用了未知用户任务：{', '.join(unknown_tasks)}。")
        if not group.get("keywords") and not group.get("aliases"):
            raise M10TargetGroupSeedError(f"{group_code} 缺少评论识别关键词或别名。")
        market_fit_rule = dict(group.get("market_fit_rule") or {})
        if not market_fit_rule.get("signals"):
            raise M10TargetGroupSeedError(f"{group_code} 缺少 market_fit_rule.signals。")
