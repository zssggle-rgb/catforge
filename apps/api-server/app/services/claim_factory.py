import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import CategoryProject, RawSkuClaim, SkuClaimResult
from app.services.factory_utils import (
    add_evidence,
    ensure_seed_assets,
    project_param_map,
    upsert_claim_result,
    upsert_param_result,
)
from app.services.utils import clean_text


def generate_claims(db: Session, project_id: str) -> dict:
    project = db.get(CategoryProject, project_id)
    if not project:
        raise ValueError("项目不存在")
    ensure_seed_assets(db, project_id, project.category_code)
    db.execute(delete(SkuClaimResult).where(SkuClaimResult.project_id == project_id))
    rows = db.execute(select(RawSkuClaim).where(RawSkuClaim.project_id == project_id)).scalars().all()

    created = 0
    derived_params = 0
    for row in rows:
        text = " ".join(part for part in [row.claim_title, row.claim_text] if part)
        extracted = extract_claim_values(text)
        for param_code, value in extracted.items():
            if value is None or param_code == "_hdmi_text":
                continue
            evidence = add_evidence(
                db,
                project_id=project_id,
                category_code=row.category_code,
                sku_code=row.sku_code,
                source_type="claim",
                source_file_id=row.source_file_id,
                raw_row_id=row.raw_row_id,
                field_name=row.claim_title or "claim_text",
                raw_value=row.claim_text,
                normalized_value={param_code: value},
                confidence=0.86,
            )
            unit = _unit_for_param(param_code)
            upsert_param_result(
                db,
                project_id=project_id,
                category_code=row.category_code,
                sku_code=row.sku_code or "",
                param_code=param_code,
                normalized_value=value,
                normalized_numeric=float(value) if isinstance(value, (int, float)) else None,
                normalized_bool=value if isinstance(value, bool) else None,
                unit=unit,
                raw_value=row.claim_text,
                confidence=0.86,
                evidence_ids=[evidence.evidence_id],
            )
            derived_params += 1

        params = project_param_map(db, project_id).get(row.sku_code or "", {})
        activated = activate_claims(text, params, extracted)
        for claim_code, confidence in activated.items():
            evidence = add_evidence(
                db,
                project_id=project_id,
                category_code=row.category_code,
                sku_code=row.sku_code,
                source_type="claim",
                source_file_id=row.source_file_id,
                raw_row_id=row.raw_row_id,
                field_name=row.claim_title or "claim_text",
                raw_value=row.claim_text,
                normalized_value={"claim_code": claim_code, "extracted": extracted},
                confidence=confidence,
            )
            upsert_claim_result(
                db,
                project_id=project_id,
                category_code=row.category_code,
                sku_code=row.sku_code or "",
                claim_code=claim_code,
                confidence=confidence,
                activation_source="claim_text_rule",
                evidence_ids=[evidence.evidence_id],
                extracted_values={k: v for k, v in extracted.items() if not k.startswith("_")},
            )
            created += 1

    # Parameter-only claims such as large screen should also activate.
    params_by_sku = project_param_map(db, project_id)
    for sku_code, params in params_by_sku.items():
        param_activated = activate_claims("", params, {})
        for claim_code, confidence in param_activated.items():
            if claim_code == "CLAIM_SMART_VOICE_EASE":
                confidence = min(confidence, 0.78)
            evidence_ids = []
            for param_code in _claim_supporting_params(claim_code):
                if param_code in params:
                    evidence_ids.extend(params[param_code].evidence_ids)
            upsert_claim_result(
                db,
                project_id=project_id,
                category_code=project.category_code,
                sku_code=sku_code,
                claim_code=claim_code,
                confidence=confidence,
                activation_source="param_rule",
                evidence_ids=evidence_ids,
                extracted_values={},
            )
            created += 1

    db.commit()
    return {
        "step": "generate_claims",
        "status": "completed",
        "counts": {
            "raw_claim_rows": len(rows),
            "claim_results": db.execute(
                select(SkuClaimResult).where(SkuClaimResult.project_id == project_id)
            ).scalars().unique().all().__len__(),
            "derived_params": derived_params,
            "rule_hits": created,
        },
        "message": "标准卖点映射完成",
    }


def extract_claim_values(text: str) -> dict:
    cleaned = clean_text(text)
    values: dict[str, int | bool | None | str] = {}

    nits = [int(float(item)) for item in re.findall(r"(\d+(?:\.\d+)?)\s*nits?", cleaned, re.I)]
    if nits:
        values["peak_brightness_nits"] = max(nits)
        values["instant_peak_brightness_nits"] = nits[0]
        if len(nits) > 1:
            values["sustained_peak_brightness_nits"] = nits[1]

    zone_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:分区|zones?)", cleaned, re.I)
    if zone_match:
        values["dimming_zones"] = int(float(zone_match.group(1)))

    hz_matches = [int(float(item)) for item in re.findall(r"(\d+(?:\.\d+)?)\s*hz", cleaned, re.I)]
    if hz_matches:
        refresh = max(value for value in hz_matches if value < 1000) if any(v < 1000 for v in hz_matches) else hz_matches[0]
        if "原生" in cleaned or "4K" in cleaned:
            values["native_refresh_rate_hz"] = refresh
        else:
            values["system_refresh_rate_hz"] = refresh
    dimming_match = re.search(r"(\d+(?:\.\d+)?)\s*hz[^，。；;]*调光", cleaned, re.I)
    if dimming_match:
        values["eye_dimming_freq_hz"] = int(float(dimming_match.group(1)))

    hdmi_match = re.search(r"(\d+)\s*[×xX*]\s*HDMI\s*2\.1", cleaned, re.I)
    if hdmi_match:
        values["hdmi_2_1_ports"] = int(hdmi_match.group(1))
    elif re.search(r"HDMI\s*2\.1|HDMI2\.1", cleaned, re.I):
        values["hdmi_2_1_ports"] = 1
    if re.search(r"mini\s*led|miniled|U\+Mini", cleaned, re.I):
        values["mini_led_flag"] = True

    ram_match = re.search(r"(\d+)\s*GB[^，。；;]*(?:RAM|内存)", cleaned, re.I)
    if ram_match:
        values["ram_gb"] = int(ram_match.group(1))
    rom_match = re.search(r"(\d+)\s*GB[^，。；;]*(?:ROM|存储)", cleaned, re.I)
    if rom_match:
        values["storage_gb"] = int(rom_match.group(1))

    return values


def activate_claims(text: str, params: dict, extracted: dict) -> dict[str, float]:
    lowered = clean_text(text).lower()
    activated: dict[str, float] = {}

    def numeric(param_code: str) -> float | None:
        if param_code in extracted and isinstance(extracted[param_code], (int, float)):
            return float(extracted[param_code])
        row = params.get(param_code)
        return row.normalized_numeric if row else None

    def boolean(param_code: str) -> bool | None:
        if param_code in extracted and isinstance(extracted[param_code], bool):
            return extracted[param_code]
        row = params.get(param_code)
        return row.normalized_bool if row else None

    if (numeric("screen_size_inch") or 0) >= 75 or any(k in lowered for k in ["大屏", "巨幕", "沉浸"]):
        activated["CLAIM_LARGE_SCREEN_IMMERSION"] = 0.9
    if boolean("mini_led_flag") is True or "mini led" in lowered or "miniled" in lowered:
        activated["CLAIM_MINI_LED_BACKLIGHT"] = 0.9
    if (numeric("peak_brightness_nits") or 0) >= 1000 or any(k.lower() in lowered for k in ["nits", "hdr", "xdr", "高亮"]):
        activated["CLAIM_HIGH_BRIGHTNESS_HDR"] = 0.88
    if (numeric("dimming_zones") or 0) >= 100 or "分区" in lowered or "控光" in lowered:
        activated["CLAIM_FINE_LOCAL_DIMMING"] = 0.87
    if max(numeric("native_refresh_rate_hz") or 0, numeric("system_refresh_rate_hz") or 0) >= 120 or "高刷" in lowered:
        activated["CLAIM_HIGH_REFRESH_RATE"] = 0.86
    if (numeric("hdmi_2_1_ports") or 0) >= 1 or "hdmi 2.1" in lowered or "hdmi2.1" in lowered:
        activated["CLAIM_HDMI_2_1_GAMING"] = 0.84
    if (numeric("eye_dimming_freq_hz") or 0) >= 1000 or any(k in lowered for k in ["护眼", "调光", "无频闪", "环境光"]):
        activated["CLAIM_EYE_CARE_COMFORT"] = 0.78 if "调光" in lowered or "护眼" in lowered else 0.68
    if any(k.lower() in lowered for k in ["ai", "智能", "语音", "流畅", "老人"]) or (numeric("ram_gb") or 0) >= 4:
        activated["CLAIM_SMART_VOICE_EASE"] = 0.78
    if any(k in lowered for k in ["音响", "音效", "环绕", "低音"]):
        activated["CLAIM_IMMERSIVE_AUDIO"] = 0.72
    return activated


def _unit_for_param(param_code: str) -> str | None:
    if param_code.endswith("_hz"):
        return "Hz"
    if param_code.endswith("_nits"):
        return "nits"
    if param_code == "dimming_zones":
        return "zones"
    if param_code == "hdmi_2_1_ports":
        return "ports"
    if param_code.endswith("_gb"):
        return "GB"
    return None


def _claim_supporting_params(claim_code: str) -> list[str]:
    mapping = {
        "CLAIM_LARGE_SCREEN_IMMERSION": ["screen_size_inch"],
        "CLAIM_MINI_LED_BACKLIGHT": ["mini_led_flag"],
        "CLAIM_HIGH_BRIGHTNESS_HDR": ["peak_brightness_nits", "instant_peak_brightness_nits", "sustained_peak_brightness_nits"],
        "CLAIM_FINE_LOCAL_DIMMING": ["dimming_zones"],
        "CLAIM_HIGH_REFRESH_RATE": ["native_refresh_rate_hz", "system_refresh_rate_hz"],
        "CLAIM_HDMI_2_1_GAMING": ["hdmi_2_1_ports"],
        "CLAIM_EYE_CARE_COMFORT": ["eye_dimming_freq_hz"],
        "CLAIM_SMART_VOICE_EASE": ["ram_gb", "storage_gb"],
    }
    return mapping.get(claim_code, [])

