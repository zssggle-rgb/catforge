import json

import pytest

from app.services.core3_real_data.constants import CORE3_M03_SEED_VERSION
from app.services.core3_real_data.param_extraction_schemas import ParamSourceType
from app.services.core3_real_data.param_seed_loader import (
    CORE_PARAM_CODES,
    StdParamSeedLoader,
    StdParamSeedValidationError,
)


def test_m03_seed_loader_loads_real_seed_and_core_params():
    result = StdParamSeedLoader().load()
    seed = result.seed
    param_codes = [item.param_code for item in seed.standard_params]

    assert seed.seed_version == CORE3_M03_SEED_VERSION
    assert result.seed_version == CORE3_M03_SEED_VERSION
    assert result.raw_version == "core3-mvp-0.2.0"
    assert result.standard_param_count == len(seed.standard_params) == 60
    assert len(param_codes) == len(set(param_codes))
    assert CORE_PARAM_CODES.issubset(set(param_codes))
    assert result.core_param_codes == sorted(CORE_PARAM_CODES)
    assert seed.metadata_json["raw_standard_param_count"] == 60


def test_m03_seed_loader_normalizes_sources_and_ignores_comment_text():
    result = StdParamSeedLoader().load()
    seed = result.seed
    source_values = {
        source_type
        for standard_param in seed.standard_params
        for source_type in standard_param.model_dump()["source_types"]
    }

    assert "comment_text" not in source_values
    assert source_values <= {"raw_param", "derived_from_claim", "model_name"}
    assert result.ignored_source_type_counts["comment_text"] > 0
    assert seed.metadata_json["ignored_source_type_counts"]["comment_text"] > 0

    claim_param = next(item for item in seed.standard_params if item.param_code == "motion_compensation_flag")
    assert ParamSourceType.DERIVED_FROM_CLAIM in claim_param.source_types
    assert "comment_text" not in claim_param.model_dump()["source_types"]


def test_m03_seed_loader_preserves_parser_metadata_without_crossing_m03_boundary():
    seed = StdParamSeedLoader().load_seed()
    refresh_rate = next(item for item in seed.standard_params if item.param_code == "native_refresh_rate_hz")

    assert refresh_rate.param_group == "picture"
    assert refresh_rate.value_parsers == ["hz"]
    assert refresh_rate.required_for_core is True
    assert refresh_rate.parser_config_json["raw_param_group"] == "picture_quality"
    assert refresh_rate.parser_config_json["mapped_claim_codes"]
    assert refresh_rate.parser_config_json["mapped_task_codes"]
    assert refresh_rate.parser_config_json["mapped_battlefield_codes"]
    model_fields = type(refresh_rate).model_fields
    assert set(model_fields) >= {
        "param_code",
        "param_name",
        "data_type",
        "param_group",
        "aliases",
        "value_parsers",
        "source_types",
    }
    assert "task_code" not in model_fields
    assert "battlefield_code" not in model_fields


def test_m03_seed_loader_validates_required_root_and_fields(tmp_path):
    missing_root_path = tmp_path / "missing_root.json"
    missing_root_path.write_text(json.dumps({"version": "test"}), encoding="utf-8")

    with pytest.raises(StdParamSeedValidationError, match="standard_params"):
        StdParamSeedLoader(missing_root_path).load()

    missing_field_path = tmp_path / "missing_field.json"
    missing_field_path.write_text(
        json.dumps(
            {
                "version": "test",
                "standard_params": [
                    {
                        "param_code": "screen_size_inch",
                        "param_name": "屏幕尺寸",
                        "data_type": "number",
                        "param_group": "display_basic",
                        "source_types": ["raw_param"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(StdParamSeedValidationError) as exc_info:
        StdParamSeedLoader(missing_field_path).load()

    assert "aliases is required" in str(exc_info.value)
    assert "value_parsers is required" in str(exc_info.value)
    assert "missing core param codes" in str(exc_info.value)


def test_m03_seed_loader_rejects_duplicate_codes_and_unknown_source(tmp_path):
    bad_seed = {
        "version": "test",
        "standard_params": [
            _param("screen_size_inch", source_types=["raw_param"]),
            _param("screen_size_inch", source_types=["comment_text", "review_note"]),
        ],
    }
    bad_seed_path = tmp_path / "bad_seed.json"
    bad_seed_path.write_text(json.dumps(bad_seed, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(StdParamSeedValidationError) as exc_info:
        StdParamSeedLoader(bad_seed_path).load()

    message = str(exc_info.value)
    assert "param_code must be unique" in message
    assert "unsupported source type: review_note" in message


def _param(param_code: str, *, source_types: list[str]) -> dict[str, object]:
    return {
        "param_code": param_code,
        "param_name": "屏幕尺寸",
        "definition": "测试参数",
        "data_type": "number",
        "param_group": "display_basic",
        "aliases": ["屏幕尺寸"],
        "keywords": ["尺寸"],
        "source_types": source_types,
        "source_priority": source_types,
        "value_parsers": ["inch"],
        "unit": "inch",
    }
