"""Read and validate the TV user-task seed used by M09."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from app.services.core3_real_data.constants import (
    CORE3_M09_EXPECTED_TASK_CODES,
    CORE3_M09_SEED_VERSION,
)
from app.services.core3_real_data.hash_utils import stable_hash


SEED_FILE_NAME = "tv_core3_mvp_seed_v0_2.json"


class M09TaskSeedError(RuntimeError):
    pass


@dataclass(frozen=True)
class M09TaskSeed:
    seed_version: str
    file_version: str
    seed_hash: str
    raw_seed: dict[str, Any]
    tasks: tuple[dict[str, Any], ...]

    @property
    def task_count(self) -> int:
        return len(self.tasks)


class M09TaskSeedLoader:
    def __init__(self, seed_path: Path | None = None) -> None:
        self.seed_path = seed_path or Path(__file__).parents[2] / "rules" / SEED_FILE_NAME

    def load(self) -> M09TaskSeed:
        if not self.seed_path.exists():
            raise M09TaskSeedError(f"M09 用户任务 seed 不存在：{self.seed_path}")
        raw_seed = json.loads(self.seed_path.read_text(encoding="utf-8"))
        self._validate_seed(raw_seed)
        return M09TaskSeed(
            seed_version=CORE3_M09_SEED_VERSION,
            file_version=str(raw_seed["version"]),
            seed_hash=stable_hash(raw_seed, version="m09_task_seed_hash_v1"),
            raw_seed=raw_seed,
            tasks=tuple(dict(item) for item in raw_seed["user_tasks"]),
        )

    def _validate_seed(self, raw_seed: Mapping[str, Any]) -> None:
        if raw_seed.get("category_code") != "TV":
            raise M09TaskSeedError("M09 用户任务 seed category_code 必须为 TV。")
        if not raw_seed.get("version"):
            raise M09TaskSeedError("M09 用户任务 seed 缺少 version。")
        tasks = list(raw_seed.get("user_tasks") or [])
        expected_codes = tuple(CORE3_M09_EXPECTED_TASK_CODES)
        actual_codes = tuple(item.get("task_code") for item in tasks)
        if actual_codes != expected_codes:
            raise M09TaskSeedError("M09 用户任务 seed 必须按 MVP 顺序覆盖 10 个固定任务。")
        if len(set(actual_codes)) != len(actual_codes):
            raise M09TaskSeedError("M09 用户任务 seed 存在重复 task_code。")
        for task in tasks:
            self._validate_task(task)

    def _validate_task(self, task: Mapping[str, Any]) -> None:
        task_code = str(task.get("task_code") or "")
        if not task_code:
            raise M09TaskSeedError("M09 用户任务 seed 存在空 task_code。")
        if not task.get("task_name"):
            raise M09TaskSeedError(f"{task_code} 缺少中文任务名称。")
        if not task.get("definition"):
            raise M09TaskSeedError(f"{task_code} 缺少任务定义。")
        score_rule = dict(task.get("score_rule") or {})
        weight_pairs = (
            ("claim", "claim_weight"),
            ("param", "param_weight"),
            ("comment", "comment_weight"),
            ("market", "market_weight"),
        )
        missing = [
            f"{short}/{long}"
            for short, long in weight_pairs
            if short not in score_rule and long not in score_rule
        ]
        if missing:
            raise M09TaskSeedError(f"{task_code} score_rule 缺少 {', '.join(missing)}。")
        total_weight = sum(_decimal(score_rule.get(short, score_rule.get(long))) for short, long in weight_pairs)
        if abs(total_weight - Decimal("1.0000")) > Decimal("0.0010"):
            raise M09TaskSeedError(f"{task_code} score_rule 四域权重总和必须为 1。")
        mapped_fields = (
            "positive_param_codes",
            "mapped_param_codes",
            "positive_claim_codes",
            "mapped_claim_codes",
            "comment_topic_codes",
            "mapped_topic_codes",
            "market_signals",
        )
        if not any(task.get(key) for key in mapped_fields):
            raise M09TaskSeedError(f"{task_code} 缺少任务映射线索，不能进入 M09。")


def _decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))
