"""Fixture helpers for Core3 real-data v2 tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.core3_real_data.constants import CORE3_TARGET_BRAND_85E7Q, CORE3_TARGET_SKU_85E7Q
from app.services.core3_real_data.hash_utils import stable_hash


CORE3_REAL_DATA_FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "core3_real_data"

WEEK_SALES_FIXTURE = "week_sales_data_85e7q_sample.json"
ATTRIBUTE_FIXTURE = "attribute_data_85e7q_sample.json"
SELLING_POINTS_FIXTURE = "selling_points_data_limited_sample.json"
COMMENT_FIXTURE = "comment_data_85e7q_sample.json"
EXPECTED_BASELINE_FIXTURE = "expected_85e7q_baseline.json"
LOCAL_VALIDATION_FIXTURE = "local_validation_fixture_v1.json"


@dataclass(frozen=True)
class Core3RealDataFixtureSet:
    week_sales_data: list[dict[str, Any]]
    attribute_data: list[dict[str, Any]]
    selling_points_data: list[dict[str, Any]]
    comment_data: list[dict[str, Any]]
    expected_baseline: dict[str, Any]

    @property
    def target_sku_code(self) -> str:
        return str(self.expected_baseline["target_sku_code"])

    def model_codes(self) -> set[str]:
        codes: set[str] = set()
        for rows in [self.week_sales_data, self.attribute_data, self.selling_points_data, self.comment_data]:
            codes.update(str(row["model_code"]) for row in rows if row.get("model_code"))
        return codes

    def target_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [row for row in rows if row.get("model_code") == self.target_sku_code]

    def same_brand_candidate_codes(self) -> set[str]:
        codes: set[str] = set()
        for rows in [self.week_sales_data, self.attribute_data, self.selling_points_data, self.comment_data]:
            for row in rows:
                model_code = row.get("model_code")
                if row.get("brand") == CORE3_TARGET_BRAND_85E7Q and model_code != CORE3_TARGET_SKU_85E7Q:
                    codes.add(str(model_code))
        return codes

    def duplicate_comment_ids(self) -> set[str]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for row in self.comment_data:
            comment_id = str(row.get("comment_id"))
            if comment_id in seen:
                duplicates.add(comment_id)
            seen.add(comment_id)
        return duplicates

    def missing_like_attribute_values(self) -> set[Any]:
        return {
            row.get("attribute_value")
            for row in self.attribute_data
            if row.get("model_code") == self.target_sku_code and row.get("attribute_value") in {None, "", "unknown", "-"}
        }

    def baseline_summary(self) -> dict[str, Any]:
        channels = sorted({row["channel"] for row in self.week_sales_data if row.get("channel")})
        platform_types = sorted({row["platform_type"] for row in self.week_sales_data if row.get("platform_type")})
        weeks = sorted({row["week"] for row in self.week_sales_data if row.get("week")})
        summary = {
            "target_sku_code": self.target_sku_code,
            "model_code_count": len(self.model_codes()),
            "market_has_target": bool(self.target_rows(self.week_sales_data)),
            "attribute_has_target": bool(self.target_rows(self.attribute_data)),
            "comment_has_target": bool(self.target_rows(self.comment_data)),
            "selling_points_has_target": bool(self.target_rows(self.selling_points_data)),
            "same_brand_candidate_count": len(self.same_brand_candidate_codes()),
            "channels": channels,
            "platform_types": platform_types,
            "weeks": weeks,
            "duplicate_comment_ids": sorted(self.duplicate_comment_ids()),
            "missing_like_values": sorted(self.missing_like_attribute_values(), key=lambda value: str(value)),
            "fixture_hash": stable_hash(
                {
                    "week_sales_data": self.week_sales_data,
                    "attribute_data": self.attribute_data,
                    "selling_points_data": self.selling_points_data,
                    "comment_data": self.comment_data,
                    "expected_baseline": self.expected_baseline,
                },
                version="fixture-85e7q-v1",
            ),
        }
        return summary


@dataclass(frozen=True)
class Core3LocalValidationFixtureSet:
    fixture: dict[str, Any]

    @property
    def target_sku_code(self) -> str:
        return str(self.fixture["target_sku_code"])

    @property
    def sku_scenarios(self) -> list[dict[str, Any]]:
        return list(self.fixture["sku_scenarios"])

    @property
    def expected_core3(self) -> list[str]:
        return list(self.fixture["expected_competitor_set"]["core3"])

    def expected_excluded(self) -> list[str]:
        return list(self.fixture["expected_competitor_set"]["exclude"])

    def sku_codes(self) -> list[str]:
        return [str(sku["sku_code"]) for sku in self.sku_scenarios]

    def scenario_by_sku(self) -> dict[str, dict[str, Any]]:
        return {str(sku["sku_code"]): sku for sku in self.sku_scenarios}

    def raw_table_rows(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "week_sales_data": self.week_sales_rows(),
            "attribute_data": self.attribute_rows(),
            "selling_points_data": self.selling_point_rows(),
            "comment_data": self.comment_rows(),
        }

    def week_sales_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        row_id = 1
        weeks = list(self.fixture["weeks"])
        for sku in self.sku_scenarios:
            market = sku["market"]
            for index, week in enumerate(weeks):
                price = int(market["base_price"])
                sales_volume = int(market["weekly_sales"][index])
                rows.append(
                    {
                        "id": row_id,
                        "model_code": sku["sku_code"],
                        "category": "彩电",
                        "brand": sku["brand"],
                        "model": sku["model_name"],
                        "date_value": week,
                        "channel": market["channel"],
                        "platform": market["platform_type"],
                        "sales_volume": sales_volume,
                        "sales_amount": sales_volume * price,
                        "avg_price": price,
                        "write_time": f"2026-06-{10 + index:02d} 10:00:00",
                    }
                )
                row_id += 1
        return rows

    def attribute_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        row_id = 1
        for sku in self.sku_scenarios:
            for attr_name, attr_value in sku["attributes"].items():
                rows.append(
                    {
                        "id": row_id,
                        "model_code": sku["sku_code"],
                        "category": "彩电",
                        "brand": sku["brand"],
                        "model": sku["model_name"],
                        "attr_name": attr_name,
                        "attr_value": attr_value,
                        "write_time": "2026-06-11 11:00:00",
                    }
                )
                row_id += 1
        return rows

    def selling_point_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        row_id = 1
        for sku in self.sku_scenarios:
            for index, claim in enumerate(sku["claims"], start=1):
                rows.append(
                    {
                        "id": row_id,
                        "model_code": sku["sku_code"],
                        "category": "彩电",
                        "brand": sku["brand"],
                        "model": sku["model_name"],
                        "variable": f"卖点{index}",
                        "selling_point": claim,
                        "write_time": "2026-06-11 12:00:00",
                    }
                )
                row_id += 1
        return rows

    def comment_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        row_id = 1
        templates = self.fixture["comment_templates"]
        for sku in self.sku_scenarios:
            for theme, count in sku["comment_theme_counts"].items():
                theme_templates = list(templates[theme])
                for index in range(int(count)):
                    comment_text = theme_templates[index % len(theme_templates)]
                    rows.append(
                        {
                            "id": row_id,
                            "model_code": sku["sku_code"],
                            "category": "彩电",
                            "brand": sku["brand"],
                            "model": sku["model_name"],
                            "platform": "京东",
                            "url_id": f"url-{sku['sku_code']}-{row_id}",
                            "comment_id": f"CMT-{sku['sku_code']}-{row_id:04d}",
                            "comment_time": f"2026-06-{12 + (index % 10):02d} 18:{index % 60:02d}:00",
                            "comment_content": comment_text,
                            "comments_segments": comment_text,
                            "primary_dim": _comment_primary_dim(theme),
                            "secondary_dim": _comment_secondary_dim(theme),
                            "third_dim": None,
                            "sentiment": _comment_sentiment(theme),
                            "write_time": f"2026-06-{12 + (index % 10):02d} 19:{index % 60:02d}:00",
                        }
                    )
                    row_id += 1
        return rows

    def baseline_summary(self) -> dict[str, Any]:
        raw_rows = self.raw_table_rows()
        per_sku_comment_count: dict[str, int] = {}
        for row in raw_rows["comment_data"]:
            sku_code = str(row["model_code"])
            per_sku_comment_count[sku_code] = per_sku_comment_count.get(sku_code, 0) + 1
        summary = {
            "fixture_id": self.fixture["fixture_id"],
            "target_sku_code": self.target_sku_code,
            "sku_count": len(self.sku_scenarios),
            "core3_expected": self.expected_core3,
            "excluded_expected": self.expected_excluded(),
            "row_counts": {table: len(rows) for table, rows in raw_rows.items()},
            "per_sku_comment_count": per_sku_comment_count,
            "roles": {sku["sku_code"]: sku["role_expected"] for sku in self.sku_scenarios},
            "fixture_hash": stable_hash(
                self.fixture,
                version="fixture-local-validation-v1",
            ),
        }
        return summary


def load_json_fixture(file_name: str, fixture_dir: Path | None = None) -> Any:
    path = (fixture_dir or CORE3_REAL_DATA_FIXTURE_DIR) / file_name
    with path.open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def load_85e7q_fixture_set(fixture_dir: Path | None = None) -> Core3RealDataFixtureSet:
    return Core3RealDataFixtureSet(
        week_sales_data=load_json_fixture(WEEK_SALES_FIXTURE, fixture_dir),
        attribute_data=load_json_fixture(ATTRIBUTE_FIXTURE, fixture_dir),
        selling_points_data=load_json_fixture(SELLING_POINTS_FIXTURE, fixture_dir),
        comment_data=load_json_fixture(COMMENT_FIXTURE, fixture_dir),
        expected_baseline=load_json_fixture(EXPECTED_BASELINE_FIXTURE, fixture_dir),
    )


def load_local_validation_fixture_set(fixture_dir: Path | None = None) -> Core3LocalValidationFixtureSet:
    return Core3LocalValidationFixtureSet(
        fixture=load_json_fixture(LOCAL_VALIDATION_FIXTURE, fixture_dir),
    )


def _comment_primary_dim(theme: str) -> str:
    if "install_service" in theme:
        return "服务体验"
    if "price" in theme:
        return "价格感知"
    return "产品体验"


def _comment_secondary_dim(theme: str) -> str:
    if "game" in theme:
        return "游戏体验"
    if "sports" in theme:
        return "体育观赛"
    if "family_movie" in theme:
        return "家庭观影"
    if "picture" in theme:
        return "画质表现"
    if "install_service" in theme:
        return "安装服务"
    if "price" in theme:
        return "价格评价"
    return "基础观看"


def _comment_sentiment(theme: str) -> str:
    if theme.endswith("_negative"):
        return "negative"
    if theme.endswith("_neutral"):
        return "neutral"
    return "positive"
