"""Read and validate the TV dimension ontology seed used by M08.5."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.services.core3_real_data.constants import (
    CORE3_M08_5_SEED_VERSION,
    CORE3_M09_EXPECTED_TASK_CODES,
    CORE3_M10_EXPECTED_TARGET_GROUP_CODES,
    CORE3_M11_EXPECTED_BATTLEFIELD_CODES,
)
from app.services.core3_real_data.hash_utils import stable_hash


SEED_FILE_NAME = "tv_core3_mvp_seed_v0_2.json"


class M085DimensionSeedError(RuntimeError):
    pass


@dataclass(frozen=True)
class M085DimensionSeed:
    seed_version: str
    file_version: str
    seed_hash: str
    raw_seed: dict[str, Any]
    tasks: tuple[dict[str, Any], ...]
    target_groups: tuple[dict[str, Any], ...]
    battlefields: tuple[dict[str, Any], ...]
    standard_claims: tuple[dict[str, Any], ...]
    standard_params: tuple[dict[str, Any], ...]
    comment_topics: tuple[dict[str, Any], ...]

    @property
    def definition_seed_count(self) -> int:
        return len(self.tasks) + len(self.target_groups) + len(self.battlefields)


class M085DimensionSeedLoader:
    def __init__(self, seed_path: Path | None = None) -> None:
        self.seed_path = seed_path or Path(__file__).parents[2] / "rules" / SEED_FILE_NAME

    def load(self) -> M085DimensionSeed:
        if not self.seed_path.exists():
            raise M085DimensionSeedError(f"M08.5 业务维度 seed 不存在：{self.seed_path}")
        raw_seed = json.loads(self.seed_path.read_text(encoding="utf-8"))
        self._validate_seed(raw_seed)
        seed_hash = stable_hash(
            {
                "version": raw_seed.get("version"),
                "user_tasks": raw_seed.get("user_tasks") or [],
                "target_groups": raw_seed.get("target_groups") or [],
                "battlefields": raw_seed.get("battlefields") or [],
                "standard_claims": raw_seed.get("standard_claims") or [],
                "standard_params": raw_seed.get("standard_params") or [],
                "comment_topics": raw_seed.get("comment_topics") or [],
            },
            version="m085_dimension_seed_hash_v1",
        )
        return M085DimensionSeed(
            seed_version=CORE3_M08_5_SEED_VERSION,
            file_version=str(raw_seed["version"]),
            seed_hash=seed_hash,
            raw_seed=raw_seed,
            tasks=tuple(dict(item) for item in raw_seed["user_tasks"]),
            target_groups=tuple(dict(item) for item in raw_seed["target_groups"]),
            battlefields=tuple(dict(item) for item in raw_seed["battlefields"]),
            standard_claims=tuple(dict(item) for item in raw_seed.get("standard_claims") or ()),
            standard_params=tuple(dict(item) for item in raw_seed.get("standard_params") or ()),
            comment_topics=tuple(dict(item) for item in raw_seed.get("comment_topics") or ()),
        )

    def _validate_seed(self, raw_seed: Mapping[str, Any]) -> None:
        if raw_seed.get("category_code") != "TV":
            raise M085DimensionSeedError("M08.5 业务维度 seed category_code 必须为 TV。")
        if not raw_seed.get("version"):
            raise M085DimensionSeedError("M08.5 业务维度 seed 缺少 version。")
        self._validate_code_list(raw_seed, "user_tasks", "task_code", CORE3_M09_EXPECTED_TASK_CODES, "用户任务")
        self._validate_code_list(
            raw_seed,
            "target_groups",
            "target_group_code",
            CORE3_M10_EXPECTED_TARGET_GROUP_CODES,
            "目标客群",
        )
        self._validate_code_list(
            raw_seed,
            "battlefields",
            "battlefield_code",
            CORE3_M11_EXPECTED_BATTLEFIELD_CODES,
            "价值战场",
        )
        self._validate_unique(raw_seed.get("standard_claims") or (), "claim_code", "标准卖点")
        self._validate_unique(raw_seed.get("standard_params") or (), "param_code", "标准参数")
        self._validate_unique(raw_seed.get("comment_topics") or (), "topic_code", "评论主题")
        if not raw_seed.get("standard_claims") or not raw_seed.get("standard_params") or not raw_seed.get("comment_topics"):
            raise M085DimensionSeedError("M08.5 需要 seed 同时包含标准卖点、标准参数和评论主题。")

    def _validate_code_list(
        self,
        raw_seed: Mapping[str, Any],
        list_key: str,
        code_key: str,
        expected_codes: tuple[str, ...],
        label_cn: str,
    ) -> None:
        rows = list(raw_seed.get(list_key) or [])
        actual_codes = tuple(str(item.get(code_key) or "") for item in rows)
        if actual_codes != tuple(expected_codes):
            raise M085DimensionSeedError(f"M08.5 seed 必须按 MVP 顺序覆盖固定{label_cn}。")
        self._validate_unique(rows, code_key, label_cn)
        for row in rows:
            code = str(row.get(code_key) or "")
            name = row.get(code_key.replace("_code", "_name")) or row.get("task_name") or row.get("battlefield_name")
            if not code or not name or not row.get("definition"):
                raise M085DimensionSeedError(f"{label_cn} {code or '<empty>'} 缺少 code、中文名称或定义。")

    @staticmethod
    def _validate_unique(rows: Any, code_key: str, label_cn: str) -> None:
        codes = [str(item.get(code_key) or "") for item in rows]
        if any(not code for code in codes):
            raise M085DimensionSeedError(f"M08.5 seed {label_cn} 存在空 code。")
        if len(codes) != len(set(codes)):
            raise M085DimensionSeedError(f"M08.5 seed {label_cn} 存在重复 code。")
