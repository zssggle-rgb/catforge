"""Guardrails for Core3 business-facing API payloads."""

from __future__ import annotations

import re
from typing import Any


class ApiResponseGuardrailError(RuntimeError):
    pass


UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
HASH_PATTERN = re.compile(r"\b[0-9a-fA-F]{40,64}\b")

FORBIDDEN_KEY_FRAGMENTS = {
    "core3_",
    "evidence_id",
    "selection_run_id",
    "component_score_id",
    "candidate_pool_id",
    "target_report_payload_id",
    "report_section_id",
    "report_export_id",
    "result_hash",
    "input_fingerprint",
    "output_hash",
    "checksum",
    "page_payload_hash",
    "source_payload",
    "raw_payload",
    "sop_trace_json",
    "display_payload_json",
}

FORBIDDEN_TEXT_FRAGMENTS = {
    "AI 认为",
    "模型判断",
    "生成过程",
    "正在思考",
    "提示词",
    "SELECT ",
    " FROM ",
    " JOIN ",
    "market_aggregate",
    "task_battlefield",
    "comment_signal",
    "display_payload_json",
    "review_required",
    "blocked",
    "week_sales_data",
    "attribute_data",
    "selling_points_data",
    "comment_data",
    "price_wavg_12m",
    "sales_volume_12m",
    "sales_amount_12m",
}

SAFE_CODE_VALUE_KEYS = {
    "category_code",
    "competitor_sku_code",
    "export_type",
    "project_id",
    "role_code",
    "section_code",
    "short_ref",
    "sku_code",
    "status_code",
    "target_sku_code",
}


class ApiResponseGuardrail:
    """Validate that business APIs do not expose technical implementation detail."""

    def validate_business_response(self, payload: Any, *, require_data_scope: bool = True) -> None:
        self._walk(payload, path="$")
        if require_data_scope and "当前" not in str(payload):
            raise ApiResponseGuardrailError("业务响应缺少数据范围说明，不能进入高层展示页。")

    def _walk(self, value: Any, *, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                key_text = str(key)
                lowered = key_text.lower()
                if any(fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS):
                    raise ApiResponseGuardrailError(f"业务响应包含内部字段：{key_text}")
                if UUID_PATTERN.search(key_text) or HASH_PATTERN.search(key_text):
                    raise ApiResponseGuardrailError(f"业务响应字段名包含内部标识：{key_text}")
                self._walk(item, path=f"{path}.{key_text}")
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                self._walk(item, path=f"{path}[{index}]")
            return
        if isinstance(value, str):
            if UUID_PATTERN.search(value) or HASH_PATTERN.search(value):
                raise ApiResponseGuardrailError(f"业务响应包含内部标识：{path}")
            upper_value = value.upper()
            key_name = path.rsplit(".", 1)[-1].lower()
            if key_name in SAFE_CODE_VALUE_KEYS:
                return
            if any(term in value for term in FORBIDDEN_TEXT_FRAGMENTS) or any(
                term in upper_value for term in {"SELECT ", " FROM ", " JOIN "}
            ):
                raise ApiResponseGuardrailError(f"业务响应包含内部过程或技术表述：{path}")
