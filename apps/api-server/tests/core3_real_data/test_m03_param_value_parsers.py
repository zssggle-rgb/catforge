from decimal import Decimal

from app.services.core3_real_data.param_extraction_schemas import ParamParserStatus
from app.services.core3_real_data.param_seed_loader import StdParamSeedLoader
from app.services.core3_real_data.param_value_parsers import (
    M03_VALUE_PRESENT,
    M03_VALUE_UNKNOWN,
    ParamValueParserContext,
    ParamValueParserRegistry,
)


def test_m03_parser_registry_registers_every_parser_declared_by_real_seed():
    seed = StdParamSeedLoader().load_seed()
    seed_parser_names = {
        parser_name
        for standard_param in seed.standard_params
        for parser_name in standard_param.value_parsers
    }
    registry = ParamValueParserRegistry()

    assert seed_parser_names <= registry.registered_parser_names
    assert {
        "inch",
        "resolution",
        "hz",
        "nits",
        "zones",
        "ports",
        "gb",
        "percentage",
        "boolean_keyword",
        "enum_keyword",
        "list_keyword",
        "string",
    } <= registry.registered_parser_names


def test_m03_core_numeric_parsers_normalize_size_resolution_brightness_and_zones():
    registry = ParamValueParserRegistry()

    inch = registry.parse("85英寸", "inch", ParamValueParserContext(clean_param_name="尺寸"))
    resolution_4k = registry.parse("3840x2160", "resolution")
    resolution_8k = registry.parse("8K", "resolution")
    nits = registry.parse("5200nits", "nits", ParamValueParserContext(clean_param_name="峰值亮度"))
    inferred_nits = registry.parse("5200", "nits", ParamValueParserContext(clean_param_name="峰值亮度"))
    exact_zones = registry.parse("3500分区", "zones")
    level_zones = registry.parse("千级分区", "zones")

    assert inch.normalized_value == {"value": 85, "unit": "inch"}
    assert inch.numeric_value == Decimal("85")
    assert resolution_4k.normalized_value == {"resolution_class": "4K", "width": 3840, "height": 2160}
    assert resolution_8k.normalized_value == {"resolution_class": "8K"}
    assert nits.normalized_value == {"value": 5200, "unit": "nits"}
    assert inferred_nits.parser_status == ParamParserStatus.UNIT_UNCERTAIN
    assert "unit_inferred" in inferred_nits.quality_flags
    assert exact_zones.normalized_value == {"value": 3500, "unit": "zones"}
    assert level_zones.normalized_value == {"level": "thousand_level", "exact": False}
    assert level_zones.numeric_value is None
    assert "zone_level_not_exact" in level_zones.quality_flags


def test_m03_hz_parser_preserves_native_system_scope_and_uncertain_high_refresh():
    registry = ParamValueParserRegistry()

    native = registry.parse(
        "144Hz",
        "hz",
        ParamValueParserContext(param_code="native_refresh_rate_hz", clean_param_name="原生刷新率"),
    )
    generic_high = registry.parse(
        "300HZ",
        "hz",
        ParamValueParserContext(clean_param_name="屏幕刷新率"),
    )

    assert native.parser_status == ParamParserStatus.PARSED
    assert native.normalized_value == {"value": 144, "unit": "Hz", "scope": "native"}
    assert generic_high.parser_status == ParamParserStatus.SCOPE_UNCERTAIN
    assert generic_high.normalized_value == {"value": 300, "unit": "Hz", "scope": "system"}
    assert "scope_uncertain" in generic_high.quality_flags


def test_m03_ports_parser_separates_hdmi_version_from_port_count():
    registry = ParamValueParserRegistry()

    version_only = registry.parse("HDMI2.1", "ports", ParamValueParserContext(clean_param_name="HDMI参数"))
    count_only = registry.parse("4", "ports", ParamValueParserContext(clean_param_name="HDMI数量"))
    version_and_count = registry.parse("4个HDMI2.1", "ports")

    assert version_only.normalized_value == {"hdmi_version": "2.1", "port_count": None}
    assert version_only.numeric_value is None
    assert "hdmi_version_without_count" in version_only.quality_flags
    assert count_only.normalized_value == {"hdmi_version": None, "port_count": 4}
    assert count_only.numeric_value == Decimal("4")
    assert version_and_count.normalized_value == {"hdmi_version": "2.1", "port_count": 4}
    assert version_and_count.numeric_value == Decimal("4")


def test_m03_gb_percentage_boolean_enum_list_and_string_parsers():
    registry = ParamValueParserRegistry()

    ram = registry.parse("4+64GB", "gb", ParamValueParserContext(param_code="ram_gb", clean_param_name="运行内存"))
    storage = registry.parse(
        "4+64GB",
        "gb",
        ParamValueParserContext(param_code="storage_gb", clean_param_name="存储容量"),
    )
    percentage = registry.parse("95% DCI-P3", "percentage")
    yes_value = registry.parse("支持", "boolean_keyword")
    no_value = registry.parse("不支持", "boolean_keyword")
    enum_value = registry.parse(
        "Mini LED背光",
        "enum_keyword",
        ParamValueParserContext(enum_values=["Mini LED", "OLED"], keywords=["背光"]),
    )
    list_value = registry.parse(
        "HDR10/HLG/Dolby Vision",
        "list_keyword",
        ParamValueParserContext(enum_values=["HDR10", "HLG", "Dolby Vision"]),
    )
    string_value = registry.parse("海信星海大模型", "string")

    assert ram.normalized_value == {"value": 4, "unit": "GB", "values_gb": [4, 64]}
    assert storage.normalized_value == {"value": 64, "unit": "GB", "values_gb": [4, 64]}
    assert percentage.normalized_value == {"value": 95, "unit": "%"}
    assert yes_value.normalized_value is True
    assert no_value.normalized_value is False
    assert enum_value.normalized_value == "Mini LED"
    assert list_value.normalized_value == ["HDR10", "HLG", "Dolby Vision"]
    assert string_value.normalized_value == "海信星海大模型"


def test_m03_unknown_values_are_not_false_except_boolean_negative_words():
    registry = ParamValueParserRegistry()

    missing_boolean = registry.parse("-", "boolean_keyword")
    missing_inch = registry.parse(None, "inch")
    false_boolean = registry.parse("无", "boolean_keyword")
    failed_number = registry.parse("没有数字", "number")

    assert missing_boolean.parser_status == ParamParserStatus.UNKNOWN
    assert missing_boolean.value_presence == M03_VALUE_UNKNOWN
    assert missing_boolean.normalized_value is None
    assert missing_inch.parser_status == ParamParserStatus.UNKNOWN
    assert missing_inch.value_presence == M03_VALUE_UNKNOWN
    assert false_boolean.parser_status == ParamParserStatus.PARSED
    assert false_boolean.value_presence == M03_VALUE_PRESENT
    assert false_boolean.normalized_value is False
    assert failed_number.parser_status == ParamParserStatus.FAILED


def test_m03_parse_with_context_uses_first_successful_parser():
    registry = ParamValueParserRegistry()
    result = registry.parse_with_context(
        "85英寸",
        ["resolution", "inch", "string"],
        ParamValueParserContext(clean_param_name="尺寸"),
    )

    assert result.parser_name == "inch"
    assert result.normalized_value == {"value": 85, "unit": "inch"}
