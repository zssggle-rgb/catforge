"""Read-only CatForge insight CLI for SKU parameter facts.

This CLI is designed for agent usage. It exposes stable, deterministic query
commands over M03B outputs without requiring the user to know module codes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from decimal import Decimal
from typing import Any, Iterable, Sequence

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import entities
from app.services.core3_real_data.constants import CORE3_M03B_RULE_VERSION
from app.services.core3_real_data.m03b_param_profile_service import M03BTierDefinition, tv_param_taxonomy_v0_1


DEFAULT_PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
DEFAULT_CATEGORY_CODE = "TV"
LATEST_BATCH = "latest"
DEFAULT_SKU_LIMIT = 50

DIMENSION_ALIASES = {
    "尺寸": "size",
    "尺寸段": "size",
    "size": "size",
    "显示": "display_tech",
    "显示技术": "display_tech",
    "display": "display_tech",
    "display_tech": "display_tech",
    "背光": "display_tech",
    "控光": "local_dimming",
    "分区": "local_dimming",
    "分区控光": "local_dimming",
    "local_dimming": "local_dimming",
    "画质": "picture_overall",
    "综合画质": "picture_overall",
    "picture": "picture_overall",
    "picture_overall": "picture_overall",
    "性能": "performance",
    "performance": "performance",
    "智能": "smart",
    "smart": "smart",
    "接口": "ports",
    "端口": "ports",
    "ports": "ports",
    "外观": "appearance",
    "appearance": "appearance",
    "能效": "energy",
    "energy": "energy",
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        with SessionLocal() as db:
            if args.command == "sku-param-profile":
                result = query_sku_param_profile(
                    db,
                    project_id=args.project_id,
                    category_code=args.category_code,
                    batch_id=args.batch_id,
                    query=args.query,
                    sku_code=args.sku_code,
                    model_name=args.model_name,
                    include_param_values=args.include_param_values,
                    param_limit=args.param_limit,
                )
            elif args.command == "tv-param-taxonomy":
                result = query_tv_param_taxonomy(
                    group=args.group,
                    search=args.search,
                    include_excluded=args.include_excluded,
                )
            elif args.command == "tier-coverage":
                result = query_tier_coverage(
                    db,
                    project_id=args.project_id,
                    category_code=args.category_code,
                    batch_id=args.batch_id,
                    dimension=args.dimension_code,
                    tier=args.tier_code,
                    query=args.query,
                    sku_limit=args.sku_limit,
                )
            elif args.command == "ask":
                result = answer_natural_language(
                    db,
                    question=" ".join(args.question),
                    project_id=args.project_id,
                    category_code=args.category_code,
                    batch_id=args.batch_id,
                    output_format=args.format,
                    sku_limit=args.sku_limit,
                )
            else:
                parser.error("missing command")
                return 2
    except CatForgeInsightError as exc:
        result = {"status": "error", "error": str(exc)}
        emit_result(result, args.format)
        return 1

    emit_result(result, args.format)
    return 0 if result.get("status") not in {"error", "not_found", "ambiguous"} else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.catforge_insight",
        description="Query CatForge SKU parameter profiles, TV parameter taxonomy, and tier coverage.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile = subparsers.add_parser("sku-param-profile", help="Query one SKU/model parameter fact profile.")
    add_common_args(profile)
    profile.add_argument("--query", help="SKU code or model name. Fuzzy model search is supported.")
    profile.add_argument("--sku-code", help="Exact SKU code, such as TV00027354.")
    profile.add_argument("--model-name", help="Exact or fuzzy model name, such as 100A4F.")
    profile.add_argument("--include-param-values", action="store_true", help="Include all extracted standard parameter values.")
    profile.add_argument("--param-limit", type=int, default=120, help="Maximum parameter values to include when --include-param-values is set.")
    add_format_arg(profile)

    taxonomy = subparsers.add_parser("tv-param-taxonomy", help="Query the TV standard parameter taxonomy.")
    taxonomy.add_argument("--group", help="Filter by parameter group, such as picture, smart, performance.")
    taxonomy.add_argument("--search", help="Search parameter code/name/raw fields.")
    taxonomy.add_argument("--include-excluded", action="store_true", help="Include raw fields intentionally excluded from standard params.")
    add_format_arg(taxonomy)

    coverage = subparsers.add_parser("tier-coverage", help="Query SKU coverage for parameter dimension tiers.")
    add_common_args(coverage)
    coverage.add_argument("--dimension-code", help="Dimension code or alias, such as display_tech, 画质, 尺寸.")
    coverage.add_argument("--tier-code", help="Tier code, tier name, or alias, such as miniled or 旗舰画质.")
    coverage.add_argument("--query", help="Natural tier query text. Matching uses dimension/tier code, Chinese names, and rule summary.")
    coverage.add_argument("--sku-limit", type=int, default=DEFAULT_SKU_LIMIT, help="Number of SKU codes to include; 0 means all.")
    add_format_arg(coverage)

    ask = subparsers.add_parser("ask", help="Route a natural-language question to the right read-only query.")
    add_common_args(ask)
    ask.add_argument("question", nargs="+", help="Natural-language question.")
    ask.add_argument("--sku-limit", type=int, default=DEFAULT_SKU_LIMIT, help="Number of SKU codes to include for tier coverage.")
    add_format_arg(ask)
    return parser


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--category-code", default=DEFAULT_CATEGORY_CODE)
    parser.add_argument("--batch-id", default=LATEST_BATCH)


def add_format_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("json", "text"), default="text")


def query_sku_param_profile(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    query: str | None = None,
    sku_code: str | None = None,
    model_name: str | None = None,
    include_param_values: bool = False,
    param_limit: int = 120,
) -> dict[str, Any]:
    resolved_batch_id = resolve_batch_id(db, project_id, category_code, batch_id, require_profile=True)
    profile = find_sku_profile(
        db,
        project_id=project_id,
        category_code=category_code,
        batch_id=resolved_batch_id,
        query=query,
        sku_code=sku_code,
        model_name=model_name,
    )
    if isinstance(profile, list):
        return {
            "status": "ambiguous",
            "message_cn": "找到多个可能的 SKU，请补充完整 SKU 编码或型号。",
            "batch_id": resolved_batch_id,
            "candidates": profile,
        }
    if profile is None:
        return {
            "status": "not_found",
            "message_cn": "没有找到该 SKU/型号的参数画像。",
            "batch_id": resolved_batch_id,
            "query": query or sku_code or model_name,
        }

    dimension_tiers = list_dimension_tiers(db, profile)
    result = {
        "status": "ok",
        "project_id": project_id,
        "category_code": category_code,
        "batch_id": resolved_batch_id,
        "rule_version": profile.rule_version,
        "sku": {
            "sku_code": profile.sku_code,
            "model_name": profile.model_name,
        },
        "summary": {
            "param_completeness": decimal_to_float(profile.param_completeness),
            "known_param_count": profile.known_param_count,
            "unknown_param_count": profile.unknown_param_count,
            "conflict_count": profile.conflict_count,
            "review_required_count": profile.review_required_count,
        },
        "dimension_tier_profile": extract_dimension_tier_profile(profile, dimension_tiers),
        "dimension_tiers": [
            {
                "dimension_code": row.dimension_code,
                "tier_code": row.tier_code,
                "tier_name": row.tier_name,
                "tier_rank": row.tier_rank,
                "explanation": row.explanation,
                "basis_values": row.basis_values_json or {},
                "quality_flags": row.quality_flags or [],
            }
            for row in dimension_tiers
        ],
        "core_params": {
            "picture": profile.core_picture_params_json or {},
            "gaming": profile.core_gaming_params_json or {},
            "system": profile.core_system_params_json or {},
            "eye_care": profile.core_eye_care_params_json or {},
        },
        "quality_summary": profile.quality_summary_json or {},
        "evidence_id_count": len(profile.evidence_ids or []),
        "profile_hash": profile.profile_hash,
    }
    if include_param_values:
        param_values = profile.param_values_json or {}
        result["param_values"] = dict(list(param_values.items())[: max(param_limit, 0)])
        result["param_value_total"] = len(param_values)
    return result


def query_tv_param_taxonomy(
    *,
    group: str | None = None,
    search: str | None = None,
    include_excluded: bool = False,
) -> dict[str, Any]:
    taxonomy = tv_param_taxonomy_v0_1()
    group_norm = normalize_token(group)
    search_norm = normalize_token(search)
    params = []
    group_counts: dict[str, int] = defaultdict(int)
    raw_field_mapping: dict[str, list[str]] = defaultdict(list)
    for param in taxonomy.standard_params:
        group_counts[param.param_group] += 1
        for raw_field in param.raw_fields:
            raw_field_mapping[raw_field].append(param.param_code)
        haystack = normalize_token(
            " ".join(
                [
                    param.param_code,
                    param.param_name,
                    param.param_group,
                    " ".join(param.raw_fields),
                    param.parser,
                    param.missing_policy,
                ]
            )
        )
        if group_norm and normalize_token(param.param_group) != group_norm:
            continue
        if search_norm and search_norm not in haystack:
            continue
        params.append(
            {
                "param_code": param.param_code,
                "param_name": param.param_name,
                "param_group": param.param_group,
                "data_type": param.data_type,
                "raw_fields": list(param.raw_fields),
                "parser": param.parser,
                "unit": param.unit,
                "missing_policy": param.missing_policy,
                "required_for_core": param.required_for_core,
                "profile_sections": list(param.profile_sections),
            }
        )
    result = {
        "status": "ok",
        "category_code": taxonomy.category_code,
        "taxonomy_version": taxonomy.taxonomy_version,
        "param_count": len(params),
        "total_param_count": len(taxonomy.standard_params),
        "group_counts": dict(sorted(group_counts.items())),
        "params": params,
        "raw_field_mapping": {field: codes for field, codes in sorted(raw_field_mapping.items())},
        "dimension_tiers": [
            {
                "dimension_code": tier.dimension_code,
                "tier_code": tier.tier_code,
                "tier_name": tier.tier_name,
                "tier_rank": tier.tier_rank,
                "rule_summary": tier.rule_summary,
            }
            for tier in taxonomy.dimension_tiers
        ],
    }
    if include_excluded:
        result["excluded_raw_fields"] = taxonomy.excluded_raw_fields
    return result


def query_tier_coverage(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    dimension: str | None = None,
    tier: str | None = None,
    query: str | None = None,
    sku_limit: int = DEFAULT_SKU_LIMIT,
) -> dict[str, Any]:
    resolved_batch_id = resolve_batch_id(db, project_id, category_code, batch_id, require_profile=True)
    taxonomy = tv_param_taxonomy_v0_1()
    matched_dimension = resolve_dimension(dimension, query)
    matched_tiers = resolve_tiers(taxonomy.dimension_tiers, dimension=matched_dimension, tier=tier, query=query)
    stmt = (
        select(entities.Core3ParamTierCoverage)
        .where(entities.Core3ParamTierCoverage.project_id == project_id)
        .where(entities.Core3ParamTierCoverage.category_code == category_code)
        .where(entities.Core3ParamTierCoverage.batch_id == resolved_batch_id)
        .where(entities.Core3ParamTierCoverage.rule_version == CORE3_M03B_RULE_VERSION)
        .where(entities.Core3ParamTierCoverage.is_current.is_(True))
        .order_by(
            entities.Core3ParamTierCoverage.dimension_code,
            entities.Core3ParamTierCoverage.tier_rank,
            entities.Core3ParamTierCoverage.tier_code,
        )
    )
    if matched_dimension:
        stmt = stmt.where(entities.Core3ParamTierCoverage.dimension_code == matched_dimension)
    if matched_tiers:
        tier_pairs = {(item.dimension_code, item.tier_code) for item in matched_tiers}
        stmt = stmt.where(
            or_(
                *[
                    and_(
                        entities.Core3ParamTierCoverage.dimension_code == dimension_code,
                        entities.Core3ParamTierCoverage.tier_code == tier_code,
                    )
                    for dimension_code, tier_code in tier_pairs
                ]
            )
        )
    rows = list(db.execute(stmt).scalars())
    coverages = []
    for row in rows:
        sku_codes = list(row.sku_codes or [])
        visible_skus = sku_codes if sku_limit == 0 else sku_codes[: max(sku_limit, 0)]
        coverages.append(
            {
                "dimension_code": row.dimension_code,
                "tier_code": row.tier_code,
                "tier_name": row.tier_name,
                "tier_rank": row.tier_rank,
                "rule_summary": row.rule_summary,
                "sku_count": row.sku_count,
                "sku_ratio": decimal_to_float(row.sku_ratio),
                "coverage_status": row.coverage_status,
                "sku_codes": visible_skus,
                "sku_codes_returned": len(visible_skus),
                "sku_codes_truncated": sku_limit != 0 and len(sku_codes) > len(visible_skus),
                "sample_sku_codes": row.sample_sku_codes or [],
            }
        )
    return {
        "status": "ok",
        "project_id": project_id,
        "category_code": category_code,
        "batch_id": resolved_batch_id,
        "query": query,
        "matched_dimension": matched_dimension,
        "matched_tier_count": len(matched_tiers),
        "coverage_count": len(coverages),
        "coverages": coverages,
    }


def answer_natural_language(
    db: Session,
    *,
    question: str,
    project_id: str,
    category_code: str,
    batch_id: str,
    output_format: str,
    sku_limit: int,
) -> dict[str, Any]:
    normalized = normalize_token(question)
    if "标准参数" in question or "参数表" in question or "参数分类" in question:
        result = query_tv_param_taxonomy(search=extract_taxonomy_search(question), include_excluded="排除" in question)
        result["routed_command"] = "tv-param-taxonomy"
        return result
    if should_route_to_tier_coverage(question, normalized):
        result = query_tier_coverage(
            db,
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            dimension=None,
            tier=None,
            query=question,
            sku_limit=sku_limit,
        )
        result["routed_command"] = "tier-coverage"
        return result

    query = extract_sku_or_model_query(question)
    result = query_sku_param_profile(
        db,
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        query=query or question,
        include_param_values=output_format == "json",
    )
    result["routed_command"] = "sku-param-profile"
    result["question"] = question
    return result


def resolve_batch_id(db: Session, project_id: str, category_code: str, batch_id: str, *, require_profile: bool) -> str:
    if batch_id != LATEST_BATCH:
        return batch_id
    if require_profile:
        profile_batch_id = db.execute(
            select(entities.Core3SkuParamProfile.batch_id)
            .where(entities.Core3SkuParamProfile.project_id == project_id)
            .where(entities.Core3SkuParamProfile.category_code == category_code)
            .where(entities.Core3SkuParamProfile.rule_version == CORE3_M03B_RULE_VERSION)
            .order_by(entities.Core3SkuParamProfile.created_at.desc(), entities.Core3SkuParamProfile.batch_id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if profile_batch_id:
            return str(profile_batch_id)
    source_batch_id = db.execute(
        select(entities.Core3SourceBatch.batch_id)
        .where(entities.Core3SourceBatch.project_id == project_id)
        .where(entities.Core3SourceBatch.category_code == category_code)
        .order_by(entities.Core3SourceBatch.created_at.desc(), entities.Core3SourceBatch.batch_id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if source_batch_id:
        return str(source_batch_id)
    raise CatForgeInsightError(f"没有找到项目 {project_id} / {category_code} 的可用批次。")


def find_sku_profile(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    query: str | None,
    sku_code: str | None,
    model_name: str | None,
) -> entities.Core3SkuParamProfile | list[dict[str, Any]] | None:
    if not any([query, sku_code, model_name]):
        raise CatForgeInsightError("查询 SKU 参数画像需要提供 --query、--sku-code 或 --model-name。")
    filters = [
        entities.Core3SkuParamProfile.project_id == project_id,
        entities.Core3SkuParamProfile.category_code == category_code,
        entities.Core3SkuParamProfile.batch_id == batch_id,
        entities.Core3SkuParamProfile.rule_version == CORE3_M03B_RULE_VERSION,
    ]
    if sku_code:
        filters.append(func.lower(entities.Core3SkuParamProfile.sku_code) == sku_code.lower())
    elif model_name:
        model_norm = model_name.strip().lower()
        filters.append(func.lower(entities.Core3SkuParamProfile.model_name).like(f"%{escape_like(model_norm)}%", escape="\\"))
    else:
        query_norm = str(query or "").strip().lower()
        filters.append(
            or_(
                func.lower(entities.Core3SkuParamProfile.sku_code) == query_norm,
                func.lower(entities.Core3SkuParamProfile.model_name) == query_norm,
                func.lower(entities.Core3SkuParamProfile.model_name).like(f"%{escape_like(query_norm)}%", escape="\\"),
            )
        )
    rows = list(
        db.execute(
            select(entities.Core3SkuParamProfile)
            .where(*filters)
            .order_by(entities.Core3SkuParamProfile.sku_code)
            .limit(11)
        ).scalars()
    )
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    exact_query = (sku_code or model_name or query or "").strip().lower()
    exact = [row for row in rows if row.sku_code.lower() == exact_query or (row.model_name or "").lower() == exact_query]
    if len(exact) == 1:
        return exact[0]
    return [{"sku_code": row.sku_code, "model_name": row.model_name} for row in rows[:10]]


def list_dimension_tiers(db: Session, profile: entities.Core3SkuParamProfile) -> list[entities.Core3SkuParamDimensionTier]:
    return list(
        db.execute(
            select(entities.Core3SkuParamDimensionTier)
            .where(entities.Core3SkuParamDimensionTier.project_id == profile.project_id)
            .where(entities.Core3SkuParamDimensionTier.category_code == profile.category_code)
            .where(entities.Core3SkuParamDimensionTier.batch_id == profile.batch_id)
            .where(entities.Core3SkuParamDimensionTier.sku_code == profile.sku_code)
            .where(entities.Core3SkuParamDimensionTier.rule_version == CORE3_M03B_RULE_VERSION)
            .where(entities.Core3SkuParamDimensionTier.is_current.is_(True))
            .order_by(entities.Core3SkuParamDimensionTier.dimension_code)
        ).scalars()
    )


def extract_dimension_tier_profile(
    profile: entities.Core3SkuParamProfile,
    dimension_tiers: Iterable[entities.Core3SkuParamDimensionTier],
) -> dict[str, str]:
    values = profile.param_values_json or {}
    tier_profile = values.get("dimension_tier_profile")
    if isinstance(tier_profile, dict):
        return {str(key): str(value) for key, value in tier_profile.items()}
    return {row.dimension_code: row.tier_code for row in dimension_tiers}


def resolve_dimension(dimension: str | None, query: str | None) -> str | None:
    candidates = [dimension] if dimension else []
    if query:
        candidates.append(query)
    for candidate in candidates:
        candidate_norm = normalize_token(candidate)
        for alias, code in DIMENSION_ALIASES.items():
            if normalize_token(alias) in candidate_norm:
                return code
        if candidate_norm in {normalize_token(code) for code in DIMENSION_ALIASES.values()}:
            return candidate_norm
    return None


def resolve_tiers(
    tiers: Sequence[M03BTierDefinition],
    *,
    dimension: str | None,
    tier: str | None,
    query: str | None,
) -> list[M03BTierDefinition]:
    if not tier and not query:
        return []
    query_text = " ".join(value for value in (tier, query) if value)
    query_norm = normalize_token(query_text)
    query_tokens = set(extract_match_tokens(query_text))
    if not query_norm and not query_tokens:
        return []
    matches = []
    for item in tiers:
        if dimension and item.dimension_code != dimension:
            continue
        identity_haystack = normalize_token(" ".join([item.dimension_code, item.tier_code, item.tier_name]))
        exact_terms = {
            normalize_token(item.dimension_code),
            normalize_token(item.tier_code),
            normalize_token(item.tier_name),
        }
        if query_norm in exact_terms or any(token and token in identity_haystack for token in query_tokens):
            matches.append(item)
    if tier and not matches:
        tier_norm = normalize_token(tier)
        matches = [
            item
            for item in tiers
            if (not dimension or item.dimension_code == dimension)
            and (normalize_token(item.tier_code) == tier_norm or normalize_token(item.tier_name) == tier_norm)
        ]
    return matches


def should_route_to_tier_coverage(question: str, normalized: str) -> bool:
    if any(word in question for word in ("档位", "覆盖", "有哪些 SKU", "哪些 SKU", "sku列表", "SKU列表")):
        return True
    tier_words = ("miniled", "oled", "lcd", "qled", "旗舰画质", "高端画质", "一级能效", "巨幕", "无分区")
    return any(word in normalized for word in tier_words)


def extract_sku_or_model_query(question: str) -> str | None:
    sku_match = re.search(r"\b[A-Z]{1,4}\d{4,}\b", question.upper())
    if sku_match:
        return sku_match.group(0)
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_+\-]*", question)
    for token in tokens:
        if any(char.isdigit() for char in token) and len(token) >= 3:
            return token
    return None


def extract_taxonomy_search(question: str) -> str | None:
    for marker in ("查", "看", "搜索"):
        if marker in question:
            tail = question.split(marker, 1)[1].strip()
            for suffix in ("标准参数", "参数表", "参数分类"):
                tail = tail.replace(suffix, "").strip()
            return None if normalize_token(tail) in {"彩电", "电视", "tv"} else tail or None
    return None


def normalize_token(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def extract_match_tokens(value: str) -> list[str]:
    stopwords = {
        "查",
        "看",
        "一下",
        "哪些",
        "哪个",
        "档位",
        "覆盖",
        "覆盖sku",
        "sku",
        "sku列表",
        "有哪些",
        "的",
        "是",
        "有",
        "多少",
        "彩电",
        "电视",
    }
    raw_tokens = re.findall(r"[A-Za-z0-9+\-]+|[\u4e00-\u9fff]+", value)
    tokens = []
    for raw_token in raw_tokens:
        token = normalize_token(raw_token)
        if not token or token in stopwords:
            continue
        for stopword in sorted(stopwords, key=len, reverse=True):
            token = token.replace(normalize_token(stopword), "")
        if len(token) >= 2:
            tokens.append(token)
    return tokens


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def emit_result(result: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(to_jsonable(result), ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(render_text(result))


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value


def render_text(result: dict[str, Any]) -> str:
    status = result.get("status")
    if status != "ok":
        return result.get("message_cn") or result.get("error") or json.dumps(to_jsonable(result), ensure_ascii=False)
    if "sku" in result:
        sku = result["sku"]
        summary = result["summary"]
        lines = [
            f"SKU 参数画像：{sku.get('model_name') or '-'} / {sku.get('sku_code')}",
            f"批次：{result['batch_id']}；完整度：{summary['param_completeness']:.2%}；已知参数：{summary['known_param_count']}；未知参数：{summary['unknown_param_count']}；冲突：{summary['conflict_count']}；需复核：{summary['review_required_count']}",
            "维度档位：",
        ]
        for item in result.get("dimension_tiers", []):
            lines.append(f"- {item['dimension_code']}: {item['tier_name']} ({item['tier_code']})")
        return "\n".join(lines)
    if "params" in result:
        lines = [
            f"彩电标准参数：{result['param_count']}/{result['total_param_count']} 个；taxonomy={result['taxonomy_version']}",
            "分组数量：" + ", ".join(f"{key}={value}" for key, value in result["group_counts"].items()),
        ]
        for item in result["params"][:80]:
            raw_fields = ", ".join(item["raw_fields"]) or "-"
            core = "核心" if item["required_for_core"] else "辅助"
            lines.append(f"- {item['param_group']} / {item['param_code']} / {item['param_name']} / {core} / 原始字段：{raw_fields}")
        if len(result["params"]) > 80:
            lines.append(f"... 还有 {len(result['params']) - 80} 个参数，使用 --format json 查看完整结果。")
        return "\n".join(lines)
    if "coverages" in result:
        lines = [f"档位覆盖：批次 {result['batch_id']}，命中 {result['coverage_count']} 个档位"]
        for item in result["coverages"]:
            sku_codes = ", ".join(item["sku_codes"]) if item["sku_codes"] else "-"
            suffix = "（已截断）" if item["sku_codes_truncated"] else ""
            lines.append(
                f"- {item['dimension_code']} / {item['tier_name']} ({item['tier_code']}): "
                f"{item['sku_count']} 个 SKU，占比 {item['sku_ratio']:.2%}；SKU：{sku_codes}{suffix}"
            )
        return "\n".join(lines)
    return json.dumps(to_jsonable(result), ensure_ascii=False, indent=2)


class CatForgeInsightError(Exception):
    """User-facing CLI error."""


if __name__ == "__main__":
    sys.exit(main())
