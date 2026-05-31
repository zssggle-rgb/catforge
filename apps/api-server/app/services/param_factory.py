import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import CategoryProject, RawSkuParam, SkuParamNormalized
from app.services.factory_utils import add_evidence, ensure_seed_assets, upsert_param_result
from app.services.utils import clean_text, is_missing, parse_number, parse_unit_number, to_bool


def detect_param_code(raw_name: str) -> str | None:
    name = raw_name.lower()
    if "屏幕刷新率" in raw_name or "系统刷新" in raw_name:
        return "system_refresh_rate_hz"
    if "刷新" in raw_name or "高刷" in raw_name:
        return "native_refresh_rate_hz"
    if "尺寸" in raw_name or "英寸" in raw_name or "inch" in name:
        return "screen_size_inch"
    if "miniled" in name or "mini led" in name or "背光" in raw_name:
        return "mini_led_flag"
    if "ram" in name or "运行内存" in raw_name or raw_name == "内存":
        return "ram_gb"
    if "rom" in name or "存储" in raw_name:
        return "storage_gb"
    if "亮度" in raw_name or "nits" in name:
        return "peak_brightness_nits"
    if "分区" in raw_name:
        return "dimming_zones"
    if "hdmi" in name and "2.1" in name:
        return "hdmi_2_1_ports"
    if "调光" in raw_name:
        return "eye_dimming_freq_hz"
    return None


def normalize_param_value(param_code: str, raw_value: str, raw_unit: str | None = None) -> tuple:
    raw = clean_text(raw_value)
    combined = f"{raw}{raw_unit or ''}"
    if is_missing(raw):
        return "unknown", None, None, None, 0.45
    if param_code == "mini_led_flag":
        parsed = to_bool(raw)
        if parsed is None:
            if re.search(r"mini\s*led|miniled", raw, flags=re.IGNORECASE):
                parsed = True
            else:
                return "unknown", None, None, None, 0.5
        return parsed, None, parsed, None, 0.95 if parsed else 0.9
    if param_code in {"screen_size_inch"}:
        value = parse_unit_number(combined, ("寸", "英寸", "inch", '"'))
        return _number_tuple(value, "inch", raw)
    if param_code in {"native_refresh_rate_hz", "system_refresh_rate_hz", "eye_dimming_freq_hz"}:
        value = parse_unit_number(combined, ("hz", "HZ", "Hz", "赫兹"))
        return _number_tuple(value, "Hz", raw)
    if param_code in {"peak_brightness_nits", "instant_peak_brightness_nits", "sustained_peak_brightness_nits"}:
        value = parse_unit_number(combined, ("nits", "nit", "尼特"))
        return _number_tuple(value, "nits", raw)
    if param_code == "dimming_zones":
        value = parse_unit_number(combined, ("分区", "zones", "区"))
        return _number_tuple(value, "zones", raw)
    if param_code == "hdmi_2_1_ports":
        ports = _parse_hdmi_ports(raw)
        return _number_tuple(ports, "ports", raw)
    if param_code in {"ram_gb", "storage_gb"}:
        value = parse_unit_number(combined, ("gb", "GB", "g", "G"))
        return _number_tuple(value, "GB", raw)
    value = parse_number(raw)
    return _number_tuple(value, None, raw)


def _number_tuple(value: float | None, unit: str | None, raw: str) -> tuple:
    if value is None:
        return "unknown", None, None, unit, 0.45
    normalized = int(value) if float(value).is_integer() else value
    return normalized, float(value), None, unit, 0.92


def _parse_hdmi_ports(text: str) -> float | None:
    text = clean_text(text)
    if is_missing(text):
        return None
    match = re.search(r"(\d+)\s*[×xX*]?\s*HDMI\s*2\.1", text, flags=re.IGNORECASE)
    if match:
        return float(match.group(1))
    if "HDMI" in text.upper() and "2.1" in text:
        return 1.0
    return parse_number(text)


def generate_params(db: Session, project_id: str) -> dict:
    project = db.get(CategoryProject, project_id)
    if not project:
        raise ValueError("项目不存在")
    ensure_seed_assets(db, project_id, project.category_code)
    db.execute(delete(SkuParamNormalized).where(SkuParamNormalized.project_id == project_id))

    rows = db.execute(
        select(RawSkuParam).where(RawSkuParam.project_id == project_id)
    ).scalars().all()
    normalized_count = 0
    unknown_count = 0
    ignored_count = 0
    for row in rows:
        if not row.sku_code or not row.raw_param_name:
            ignored_count += 1
            continue
        param_code = detect_param_code(row.raw_param_name)
        if not param_code:
            ignored_count += 1
            continue
        normalized_value, numeric_value, bool_value, unit, confidence = normalize_param_value(
            param_code, row.raw_param_value or "", row.raw_unit
        )
        if normalized_value == "unknown":
            unknown_count += 1
        evidence = add_evidence(
            db,
            project_id=project_id,
            category_code=row.category_code,
            sku_code=row.sku_code,
            source_type="param",
            source_file_id=row.source_file_id,
            raw_row_id=row.raw_row_id,
            field_name=row.raw_param_name,
            raw_value=row.raw_param_value,
            normalized_value={param_code: normalized_value},
            confidence=confidence,
        )
        upsert_param_result(
            db,
            project_id=project_id,
            category_code=row.category_code,
            sku_code=row.sku_code,
            param_code=param_code,
            normalized_value=normalized_value,
            normalized_numeric=numeric_value,
            normalized_bool=bool_value,
            unit=unit,
            raw_value=row.raw_param_value,
            confidence=confidence,
            evidence_ids=[evidence.evidence_id],
        )
        normalized_count += 1

    db.commit()
    return {
        "step": "generate_params",
        "status": "completed",
        "counts": {
            "raw_param_rows": len(rows),
            "normalized_params": normalized_count,
            "unknown_values": unknown_count,
            "ignored_rows": ignored_count,
        },
        "message": "标准参数归一完成",
    }

