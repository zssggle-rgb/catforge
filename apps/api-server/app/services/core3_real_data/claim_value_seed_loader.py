"""Read and validate the TV claim value seed used by M11.5."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.services.core3_real_data.battlefield_seed_loader import SEED_FILE_NAME
from app.services.core3_real_data.constants import (
    CORE3_M11_5_BATTLEFIELD_SEED_VERSION,
    CORE3_M11_5_CLAIM_SEED_VERSION,
    CORE3_M11_5_EXPECTED_CLAIM_CODES,
    CORE3_M11_EXPECTED_BATTLEFIELD_CODES,
)
from app.services.core3_real_data.hash_utils import stable_hash


class M115ClaimValueSeedError(RuntimeError):
    pass


@dataclass(frozen=True)
class M115ClaimValueSeed:
    claim_seed_version: str
    battlefield_seed_version: str
    file_version: str
    claim_seed_hash: str
    battlefield_seed_hash: str
    raw_seed: dict[str, Any]
    standard_claims: tuple[dict[str, Any], ...]
    battlefields: tuple[dict[str, Any], ...]
    claims_by_code: dict[str, dict[str, Any]]
    battlefields_by_code: dict[str, dict[str, Any]]
    battlefield_claim_codes: dict[str, tuple[str, ...]]
    mapped_battlefields_by_claim: dict[str, tuple[str, ...]]

    @property
    def claim_count(self) -> int:
        return len(self.standard_claims)

    @property
    def battlefield_count(self) -> int:
        return len(self.battlefields)


class M115ClaimValueSeedLoader:
    def __init__(self, seed_path: Path | None = None) -> None:
        self.seed_path = seed_path or Path(__file__).parents[2] / "rules" / SEED_FILE_NAME

    def load(self) -> M115ClaimValueSeed:
        if not self.seed_path.exists():
            raise M115ClaimValueSeedError(f"M11.5 卖点价值 seed 不存在：{self.seed_path}")
        raw_seed = json.loads(self.seed_path.read_text(encoding="utf-8"))
        self._validate_seed(raw_seed)
        claims = tuple(dict(item) for item in raw_seed["standard_claims"])
        battlefields = tuple(dict(item) for item in raw_seed["battlefields"])
        claims_by_code = {str(item["claim_code"]): item for item in claims}
        battlefields_by_code = {str(item["battlefield_code"]): item for item in battlefields}
        return M115ClaimValueSeed(
            claim_seed_version=CORE3_M11_5_CLAIM_SEED_VERSION,
            battlefield_seed_version=CORE3_M11_5_BATTLEFIELD_SEED_VERSION,
            file_version=str(raw_seed["version"]),
            claim_seed_hash=stable_hash(claims, version="m11_5_claim_seed_hash_v1"),
            battlefield_seed_hash=stable_hash(battlefields, version="m11_5_battlefield_seed_hash_v1"),
            raw_seed=raw_seed,
            standard_claims=claims,
            battlefields=battlefields,
            claims_by_code=claims_by_code,
            battlefields_by_code=battlefields_by_code,
            battlefield_claim_codes={
                code: tuple(str(claim_code) for claim_code in battlefields_by_code[code].get("core_claim_codes") or ())
                for code in CORE3_M11_EXPECTED_BATTLEFIELD_CODES
            },
            mapped_battlefields_by_claim={
                code: tuple(str(item) for item in claims_by_code[code].get("mapped_battlefield_codes") or ())
                for code in CORE3_M11_5_EXPECTED_CLAIM_CODES
            },
        )

    def _validate_seed(self, raw_seed: Mapping[str, Any]) -> None:
        if raw_seed.get("category_code") != "TV":
            raise M115ClaimValueSeedError("M11.5 seed category_code 必须为 TV。")
        if not raw_seed.get("version"):
            raise M115ClaimValueSeedError("M11.5 seed 缺少 version。")
        claims = list(raw_seed.get("standard_claims") or [])
        battlefields = list(raw_seed.get("battlefields") or [])
        claim_codes = tuple(str(item.get("claim_code") or "") for item in claims)
        battlefield_codes = tuple(str(item.get("battlefield_code") or "") for item in battlefields)
        if claim_codes != tuple(CORE3_M11_5_EXPECTED_CLAIM_CODES):
            raise M115ClaimValueSeedError("M11.5 seed 必须按 MVP 顺序覆盖 20 个固定标准卖点。")
        if battlefield_codes != tuple(CORE3_M11_EXPECTED_BATTLEFIELD_CODES):
            raise M115ClaimValueSeedError("M11.5 seed 必须按 MVP 顺序覆盖 10 个固定价值战场。")
        if len(set(claim_codes)) != len(claim_codes):
            raise M115ClaimValueSeedError("M11.5 seed 存在重复 claim_code。")
        known_claims = set(CORE3_M11_5_EXPECTED_CLAIM_CODES)
        known_battlefields = set(CORE3_M11_EXPECTED_BATTLEFIELD_CODES)
        for claim in claims:
            self._validate_claim(claim, known_battlefields)
        for battlefield in battlefields:
            self._validate_battlefield(battlefield, known_claims)

    def _validate_claim(self, claim: Mapping[str, Any], known_battlefields: set[str]) -> None:
        claim_code = str(claim.get("claim_code") or "")
        if not claim.get("claim_name"):
            raise M115ClaimValueSeedError(f"{claim_code} 缺少中文卖点名称。")
        if not claim.get("claim_group"):
            raise M115ClaimValueSeedError(f"{claim_code} 缺少 claim_group。")
        if not claim.get("definition"):
            raise M115ClaimValueSeedError(f"{claim_code} 缺少卖点定义。")
        mapped = set(str(item) for item in claim.get("mapped_battlefield_codes") or ())
        unknown = sorted(mapped - known_battlefields)
        if unknown:
            raise M115ClaimValueSeedError(f"{claim_code} 引用了未知价值战场：{', '.join(unknown)}。")
        if not claim.get("supporting_param_codes") and not claim.get("comment_topic_codes"):
            raise M115ClaimValueSeedError(f"{claim_code} 缺少参数或评论主题映射。")

    def _validate_battlefield(self, battlefield: Mapping[str, Any], known_claims: set[str]) -> None:
        battlefield_code = str(battlefield.get("battlefield_code") or "")
        if not battlefield.get("battlefield_name"):
            raise M115ClaimValueSeedError(f"{battlefield_code} 缺少中文战场名称。")
        core_claims = set(str(item) for item in battlefield.get("core_claim_codes") or ())
        if not core_claims:
            raise M115ClaimValueSeedError(f"{battlefield_code} 缺少 core_claim_codes。")
        unknown = sorted(core_claims - known_claims)
        if unknown:
            raise M115ClaimValueSeedError(f"{battlefield_code} 引用了未知标准卖点：{', '.join(unknown)}。")
