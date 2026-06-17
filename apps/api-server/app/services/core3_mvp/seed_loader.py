from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.schemas.core3_mvp import Core3SeedCatalog

DEFAULT_SEED_PATH = (
    Path(__file__).resolve().parents[2] / "rules" / "tv_core3_mvp_seed_v0_2.json"
)

MIN_COUNTS = {
    "standard_params": 35,
    "standard_claims": 18,
    "comment_topics": 15,
    "user_tasks": 9,
    "target_groups": 8,
    "battlefields": 9,
}

REQUIRED_PARSERS = {
    "inch",
    "hz",
    "nits",
    "zones",
    "gb",
    "ports",
    "resolution",
    "percentage",
    "watt",
    "ms",
    "boolean_keyword",
    "enum_keyword",
}

SKU_LEVEL_FORBIDDEN_KEYS = {
    "sku_code",
    "target_sku_code",
    "candidate_sku_code",
    "competitor_sku_code",
    "brand",
    "model_name",
    "price_latest",
    "price_wavg_12m",
    "sales_volume_12m",
    "sales_amount_12m",
    "score",
    "confidence",
    "review_status",
    "evidence_ids",
    "evidence_card",
    "result_id",
    "profile_id",
    "feature_id",
    "candidate_id",
}


class Core3SeedValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("Core3 seed validation failed: " + "; ".join(errors))
        self.errors = errors


def load_core3_seed(path: str | Path | None = None) -> Core3SeedCatalog:
    seed_path = Path(path) if path else DEFAULT_SEED_PATH
    data = json.loads(seed_path.read_text(encoding="utf-8"))
    catalog = Core3SeedCatalog.model_validate(data)
    result = validate_core3_seed(catalog, raw_data=data)
    if not result["valid"]:
        raise Core3SeedValidationError(result["errors"])
    return catalog


def validate_core3_seed(
    seed: Core3SeedCatalog | dict[str, Any],
    *,
    raw_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    catalog: Core3SeedCatalog | None
    try:
        catalog = seed if isinstance(seed, Core3SeedCatalog) else Core3SeedCatalog.model_validate(seed)
    except ValidationError as exc:
        return {"valid": False, "errors": [str(exc)], "counts": {}}

    data = raw_data if raw_data is not None else catalog.model_dump()
    counts = {
        "standard_params": len(catalog.standard_params),
        "standard_claims": len(catalog.standard_claims),
        "comment_topics": len(catalog.comment_topics),
        "user_tasks": len(catalog.user_tasks),
        "target_groups": len(catalog.target_groups),
        "battlefields": len(catalog.battlefields),
    }
    for section, minimum in MIN_COUNTS.items():
        if counts[section] < minimum:
            errors.append(f"{section} count {counts[section]} is below minimum {minimum}")

    code_sets = {
        "param": _unique_codes([item.param_code for item in catalog.standard_params], "param", errors),
        "claim": _unique_codes([item.claim_code for item in catalog.standard_claims], "claim", errors),
        "topic": _unique_codes([item.topic_code for item in catalog.comment_topics], "topic", errors),
        "task": _unique_codes([item.task_code for item in catalog.user_tasks], "task", errors),
        "target_group": _unique_codes(
            [item.target_group_code for item in catalog.target_groups],
            "target_group",
            errors,
        ),
        "battlefield": _unique_codes(
            [item.battlefield_code for item in catalog.battlefields],
            "battlefield",
            errors,
        ),
    }

    _validate_common_assets(data, errors)
    _validate_forbidden_keys(data, errors)
    _validate_param_refs(catalog, code_sets, errors)
    _validate_claim_refs(catalog, code_sets, errors)
    _validate_topic_refs(catalog, code_sets, errors)
    _validate_task_refs(catalog, code_sets, errors)
    _validate_target_group_refs(catalog, code_sets, errors)
    _validate_battlefield_refs(catalog, code_sets, errors)
    _validate_required_parsers(catalog, errors)

    return {"valid": not errors, "errors": errors, "counts": counts}


def _unique_codes(codes: list[str], label: str, errors: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for code in codes:
        if code in seen:
            duplicates.add(code)
        seen.add(code)
    if duplicates:
        errors.append(f"duplicate {label} codes: {sorted(duplicates)}")
    return seen


def _validate_common_assets(data: dict[str, Any], errors: list[str]) -> None:
    for section in MIN_COUNTS:
        for index, item in enumerate(data.get(section, [])):
            label = f"{section}[{index}]"
            if not _first_present(item, ("param_code", "claim_code", "topic_code", "task_code", "target_group_code", "battlefield_code")):
                errors.append(f"{label} missing code field")
            if not _first_present(item, ("param_name", "claim_name", "topic_name", "task_name", "target_group_name", "battlefield_name")):
                errors.append(f"{label} missing name field")
            for field in ["definition", "aliases", "keywords", "source_types", "evidence_requirement"]:
                if not item.get(field):
                    errors.append(f"{label} missing non-empty {field}")
            if not any(key.startswith("mapped_") for key in item):
                errors.append(f"{label} missing mapped_* field")


def _validate_forbidden_keys(value: Any, errors: list[str], path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in SKU_LEVEL_FORBIDDEN_KEYS:
                errors.append(f"seed contains SKU-level field {child_path}")
            _validate_forbidden_keys(child, errors, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_forbidden_keys(child, errors, f"{path}[{index}]")


def _validate_param_refs(catalog: Core3SeedCatalog, code_sets: dict[str, set[str]], errors: list[str]) -> None:
    for item in catalog.standard_params:
        _check_refs(item.param_code, "mapped_claim_codes", item.mapped_claim_codes, code_sets["claim"], errors)
        _check_refs(item.param_code, "mapped_task_codes", item.mapped_task_codes, code_sets["task"], errors)
        _check_refs(
            item.param_code,
            "mapped_battlefield_codes",
            item.mapped_battlefield_codes,
            code_sets["battlefield"],
            errors,
        )


def _validate_claim_refs(catalog: Core3SeedCatalog, code_sets: dict[str, set[str]], errors: list[str]) -> None:
    for item in catalog.standard_claims:
        _check_refs(item.claim_code, "supporting_param_codes", item.supporting_param_codes, code_sets["param"], errors)
        _check_refs(item.claim_code, "comment_topic_codes", item.comment_topic_codes, code_sets["topic"], errors)
        _check_refs(item.claim_code, "mapped_param_codes", item.mapped_param_codes, code_sets["param"], errors)
        _check_refs(item.claim_code, "mapped_task_codes", item.mapped_task_codes, code_sets["task"], errors)
        _check_refs(
            item.claim_code,
            "mapped_battlefield_codes",
            item.mapped_battlefield_codes,
            code_sets["battlefield"],
            errors,
        )
        for param_code in _extract_activation_param_refs(item.activation_rule):
            if param_code not in code_sets["param"]:
                errors.append(f"{item.claim_code}.activation_rule references unknown param {param_code}")


def _validate_topic_refs(catalog: Core3SeedCatalog, code_sets: dict[str, set[str]], errors: list[str]) -> None:
    for item in catalog.comment_topics:
        _check_refs(item.topic_code, "mapped_claim_codes", item.mapped_claim_codes, code_sets["claim"], errors)
        _check_refs(item.topic_code, "mapped_task_codes", item.mapped_task_codes, code_sets["task"], errors)
        _check_refs(
            item.topic_code,
            "mapped_battlefield_codes",
            item.mapped_battlefield_codes,
            code_sets["battlefield"],
            errors,
        )


def _validate_task_refs(catalog: Core3SeedCatalog, code_sets: dict[str, set[str]], errors: list[str]) -> None:
    for item in catalog.user_tasks:
        _check_refs(item.task_code, "positive_claim_codes", item.positive_claim_codes, code_sets["claim"], errors)
        _check_refs(item.task_code, "positive_param_codes", item.positive_param_codes, code_sets["param"], errors)
        _check_refs(item.task_code, "comment_topic_codes", item.comment_topic_codes, code_sets["topic"], errors)
        _check_refs(
            item.task_code,
            "default_target_group_codes",
            item.default_target_group_codes,
            code_sets["target_group"],
            errors,
        )
        _check_refs(item.task_code, "battlefield_codes", item.battlefield_codes, code_sets["battlefield"], errors)
        _check_refs(item.task_code, "mapped_claim_codes", item.mapped_claim_codes, code_sets["claim"], errors)
        _check_refs(item.task_code, "mapped_param_codes", item.mapped_param_codes, code_sets["param"], errors)
        _check_refs(item.task_code, "mapped_topic_codes", item.mapped_topic_codes, code_sets["topic"], errors)
        _check_refs(
            item.task_code,
            "mapped_target_group_codes",
            item.mapped_target_group_codes,
            code_sets["target_group"],
            errors,
        )
        _check_refs(
            item.task_code,
            "mapped_battlefield_codes",
            item.mapped_battlefield_codes,
            code_sets["battlefield"],
            errors,
        )


def _validate_target_group_refs(
    catalog: Core3SeedCatalog,
    code_sets: dict[str, set[str]],
    errors: list[str],
) -> None:
    for item in catalog.target_groups:
        _check_refs(item.target_group_code, "source_task_codes", item.source_task_codes, code_sets["task"], errors)
        _check_refs(item.target_group_code, "mapped_task_codes", item.mapped_task_codes, code_sets["task"], errors)
        _check_refs(
            item.target_group_code,
            "mapped_battlefield_codes",
            item.mapped_battlefield_codes,
            code_sets["battlefield"],
            errors,
        )


def _validate_battlefield_refs(
    catalog: Core3SeedCatalog,
    code_sets: dict[str, set[str]],
    errors: list[str],
) -> None:
    for item in catalog.battlefields:
        _check_refs(item.battlefield_code, "core_task_codes", item.core_task_codes, code_sets["task"], errors)
        _check_refs(item.battlefield_code, "core_claim_codes", item.core_claim_codes, code_sets["claim"], errors)
        _check_refs(item.battlefield_code, "core_param_codes", item.core_param_codes, code_sets["param"], errors)
        _check_refs(item.battlefield_code, "comment_topic_codes", item.comment_topic_codes, code_sets["topic"], errors)
        _check_refs(item.battlefield_code, "mapped_task_codes", item.mapped_task_codes, code_sets["task"], errors)
        _check_refs(item.battlefield_code, "mapped_claim_codes", item.mapped_claim_codes, code_sets["claim"], errors)
        _check_refs(item.battlefield_code, "mapped_param_codes", item.mapped_param_codes, code_sets["param"], errors)
        _check_refs(item.battlefield_code, "mapped_topic_codes", item.mapped_topic_codes, code_sets["topic"], errors)


def _validate_required_parsers(catalog: Core3SeedCatalog, errors: list[str]) -> None:
    parsers = {parser for item in catalog.standard_params for parser in item.value_parsers}
    missing = REQUIRED_PARSERS - parsers
    if missing:
        errors.append(f"missing required value parsers: {sorted(missing)}")


def _check_refs(
    owner: str,
    field: str,
    values: list[str],
    known: set[str],
    errors: list[str],
) -> None:
    unknown = sorted(set(values) - known)
    if unknown:
        errors.append(f"{owner}.{field} references unknown codes: {unknown}")


def _first_present(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if item.get(key):
            return item[key]
    return None


def _extract_activation_param_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        if isinstance(value.get("param"), str):
            refs.add(value["param"])
        for child in value.values():
            refs.update(_extract_activation_param_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.update(_extract_activation_param_refs(child))
    return refs
