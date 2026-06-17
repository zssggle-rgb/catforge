from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CategoryProject,
    RawMarketFact,
    RawSkuClaim,
    RawSkuComment,
    RawSkuMaster,
    RawSkuParam,
)

UNKNOWN_STRINGS = {"", "-", "null", "none", "unknown", "nan", "na", "n/a", "未知", "无", "空"}


class Core3ProjectNotFound(ValueError):
    pass


class Core3SkuNotFound(ValueError):
    pass


class Core3MultipleSkuMatches(ValueError):
    def __init__(self, query: str, candidates: list[dict[str, Any]]) -> None:
        super().__init__("型号匹配多个 SKU")
        self.query = query
        self.candidates = candidates


@dataclass(frozen=True)
class Core3InputBundle:
    project: CategoryProject
    sku_master: list[RawSkuMaster]
    market_facts: list[RawMarketFact]
    params: list[RawSkuParam]
    claims: list[RawSkuClaim]
    comments: list[RawSkuComment]
    evidence_index: dict[str, list[str]]


def is_unknown(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip().casefold() in UNKNOWN_STRINGS


def load_project_input(db: Session, project_id: str) -> Core3InputBundle:
    project = db.get(CategoryProject, project_id)
    if not project:
        raise Core3ProjectNotFound("项目不存在")
    return Core3InputBundle(
        project=project,
        sku_master=list(
            db.execute(select(RawSkuMaster).where(RawSkuMaster.project_id == project_id)).scalars()
        ),
        market_facts=list(
            db.execute(select(RawMarketFact).where(RawMarketFact.project_id == project_id)).scalars()
        ),
        params=list(db.execute(select(RawSkuParam).where(RawSkuParam.project_id == project_id)).scalars()),
        claims=list(db.execute(select(RawSkuClaim).where(RawSkuClaim.project_id == project_id)).scalars()),
        comments=list(
            db.execute(select(RawSkuComment).where(RawSkuComment.project_id == project_id)).scalars()
        ),
        evidence_index={},
    )


def data_status(db: Session, project_id: str) -> dict[str, Any]:
    bundle = load_project_input(db, project_id)
    sku_codes = _distinct_known(row.sku_code for row in bundle.sku_master)
    brand_count = len(_distinct_known(row.brand for row in bundle.sku_master))
    market_fact_count = _count(db, RawMarketFact, project_id)
    param_row_count = _count(db, RawSkuParam, project_id)
    claim_row_count = _count(db, RawSkuClaim, project_id)
    comment_row_count = _count(db, RawSkuComment, project_id)
    missing_summary = {
        "missing_market_sku_count": _missing_count(sku_codes, _sku_codes_with_market(bundle.market_facts)),
        "missing_price_sku_count": _missing_count(sku_codes, _sku_codes_with_price(bundle.market_facts)),
        "missing_sales_sku_count": _missing_count(sku_codes, _sku_codes_with_sales(bundle.market_facts)),
        "missing_param_sku_count": _missing_count(sku_codes, _sku_codes_with_rows(bundle.params)),
        "missing_claim_sku_count": _missing_count(sku_codes, _sku_codes_with_rows(bundle.claims)),
        "missing_comment_sku_count": _missing_count(sku_codes, _sku_codes_with_rows(bundle.comments)),
    }
    return {
        "project_id": project_id,
        "category_code": bundle.project.category_code,
        "status": _coverage_status(len(sku_codes), market_fact_count, param_row_count, claim_row_count),
        "sku_count": len(sku_codes),
        "brand_count": brand_count,
        "channel_count": len(_channels(bundle)),
        "market_fact_count": market_fact_count,
        "param_row_count": param_row_count,
        "claim_row_count": claim_row_count,
        "comment_row_count": comment_row_count,
        "missing_summary": missing_summary,
        "latest_run": None,
    }


def resolve_sku_code(db: Session, project_id: str, sku_or_model: str) -> dict[str, Any]:
    query = str(sku_or_model or "").strip()
    if is_unknown(query):
        raise ValueError("请输入有效的 sku_code 或型号")
    bundle = load_project_input(db, project_id)
    rows = [row for row in bundle.sku_master if not is_unknown(row.sku_code)]
    lowered = query.casefold()
    match_groups = [
        ("sku_code_exact", [row for row in rows if _same(row.sku_code, query)]),
        ("model_name_exact", [row for row in rows if _same(row.model_name, query)]),
        (
            "model_name_contains",
            [row for row in rows if not is_unknown(row.model_name) and lowered in str(row.model_name).casefold()],
        ),
    ]
    for match_type, matches in match_groups:
        unique = _unique_master_rows(matches)
        if len(unique) == 1:
            return _resolved(query, unique[0], match_type)
        if len(unique) > 1:
            raise Core3MultipleSkuMatches(query, [_candidate(row, match_type) for row in unique])
    raise Core3SkuNotFound("SKU 或型号不存在")


def _count(db: Session, model: type, project_id: str) -> int:
    return int(
        db.execute(select(func.count()).select_from(model).where(model.project_id == project_id)).scalar_one()
    )


def _coverage_status(sku_count: int, market_count: int, param_count: int, claim_count: int) -> str:
    if sku_count == 0:
        return "degraded"
    if market_count == 0 or param_count == 0 or claim_count == 0:
        return "degraded"
    return "ready"


def _distinct_known(values: Any) -> set[str]:
    return {str(value).strip() for value in values if not is_unknown(value)}


def _missing_count(all_skus: set[str], present_skus: set[str]) -> int:
    return len(all_skus - present_skus)


def _sku_codes_with_rows(rows: list[Any]) -> set[str]:
    return _distinct_known(row.sku_code for row in rows)


def _sku_codes_with_market(rows: list[RawMarketFact]) -> set[str]:
    return _distinct_known(row.sku_code for row in rows)


def _sku_codes_with_price(rows: list[RawMarketFact]) -> set[str]:
    output: set[str] = set()
    for row in rows:
        if is_unknown(row.sku_code):
            continue
        if row.avg_price is not None or (row.sales_amount is not None and row.sales_volume not in {None, 0}):
            output.add(str(row.sku_code).strip())
    return output


def _sku_codes_with_sales(rows: list[RawMarketFact]) -> set[str]:
    output: set[str] = set()
    for row in rows:
        if is_unknown(row.sku_code):
            continue
        if row.sales_volume is not None and row.sales_volume > 0:
            output.add(str(row.sku_code).strip())
    return output


def _channels(bundle: Core3InputBundle) -> set[str]:
    values: list[Any] = []
    for row in bundle.market_facts:
        values.extend([row.channel_group, row.channel_type, row.channel_name])
    for row in bundle.params:
        values.append(row.source_channel)
    for row in bundle.claims:
        values.append(row.source_channel)
    for row in bundle.comments:
        values.append(row.platform)
    return _distinct_known(values)


def _same(value: Any, expected: str) -> bool:
    return not is_unknown(value) and str(value).strip().casefold() == expected.casefold()


def _unique_master_rows(rows: list[RawSkuMaster]) -> list[RawSkuMaster]:
    seen: set[str] = set()
    output: list[RawSkuMaster] = []
    for row in rows:
        key = str(row.sku_code).strip()
        if key not in seen:
            output.append(row)
            seen.add(key)
    return output


def _resolved(query: str, row: RawSkuMaster, match_type: str) -> dict[str, Any]:
    return {
        "input": query,
        "sku_code": row.sku_code,
        "brand": row.brand,
        "model_name": row.model_name,
        "series": row.series,
        "match_type": match_type,
        "candidates": [],
    }


def _candidate(row: RawSkuMaster, match_type: str) -> dict[str, Any]:
    return {
        "sku_code": row.sku_code,
        "brand": row.brand,
        "model_name": row.model_name,
        "series": row.series,
        "match_type": match_type,
    }
