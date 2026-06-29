from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

from app.cli import catforge_publish
from app.services.core3_real_data.publish.base_client import InMemoryBaseClient
from app.services.core3_real_data.publish.base_publisher import BaseWorkbenchPublisher
from app.services.core3_real_data.publish.base_schema import SKU_OVERVIEW, WORKBENCH_TABLES
from app.services.core3_real_data.publish.base_schema_manager import BaseSchemaManager
from app.services.core3_real_data.publish.mappers import BaseRecordMapper
from app.services.core3_real_data.publish.schemas import PublishResult, ScopeSyncResult
from app.services.core3_real_data.publish.sync_state import BaseWorkbenchConfig


def test_base_record_mapper_outputs_business_fields_and_unique_key() -> None:
    table = WORKBENCH_TABLES[SKU_OVERVIEW]
    mapped = BaseRecordMapper().map_record(
        table,
        {
            "batch_id": "m00_1",
            "category_code": "TV",
            "sku_code": "TV001",
            "brand_name": "海信",
            "model_name": "65E7Q",
            "screen_size_inch": 65,
            "weighted_price": "5949.3",
        },
    )

    assert mapped["unique_key"] == "m00_1|TV|TV001"
    assert mapped["批次ID"] == "m00_1"
    assert mapped["品牌"] == "海信"
    assert mapped["型号"] == "65E7Q"
    assert mapped["尺寸"] == 65.0
    assert mapped["均价"] == 5949.3


def test_schema_manager_creates_phase_one_tables_fields_and_views() -> None:
    client = InMemoryBaseClient()
    result = BaseSchemaManager(client).init_workbench(base_name="小奥家电市场分析工作台")

    assert result.base_token == client.base_token
    assert set(result.table_map) == set(WORKBENCH_TABLES)
    assert len(client.tables) == len(WORKBENCH_TABLES)
    for scope, table_id in result.table_map.items():
        field_names = {field["name"] for field in client.fields[table_id]}
        assert field_names == {field.name for field in WORKBENCH_TABLES[scope].fields}
    assert any(view["name"] == "SKU总览-按品牌" for views in client.views.values() for view in views)


def test_publisher_dry_run_does_not_write_records() -> None:
    client = InMemoryBaseClient()
    extractor = _FakeExtractor(
        records={
            SKU_OVERVIEW: [
                {
                    "batch_id": "m00_1",
                    "category_code": "TV",
                    "sku_code": "TV001",
                    "brand_name": "海信",
                    "model_name": "65E7Q",
                }
            ]
        }
    )
    publisher = _publisher(client=client, extractor=extractor)

    result = publisher.sync_scope(scope=SKU_OVERVIEW, batch_id="latest", dry_run=True)

    assert result.status == "dry_run"
    assert result.extracted_count == 1
    assert client.records == {}


def test_publisher_upserts_by_unique_key_without_duplicates() -> None:
    client = InMemoryBaseClient()
    rows = [
        {
            "batch_id": "m00_1",
            "category_code": "TV",
            "sku_code": "TV001",
            "brand_name": "海信",
            "model_name": "65E7Q",
            "weighted_price": 5949,
        }
    ]
    extractor = _FakeExtractor(records={SKU_OVERVIEW: rows})
    publisher = _publisher(client=client, extractor=extractor)

    first = publisher.sync_scope(scope=SKU_OVERVIEW, batch_id="latest", allow_schema_update=True)
    rows[0]["weighted_price"] = 5999
    second = publisher.sync_scope(scope=SKU_OVERVIEW, batch_id="latest", allow_schema_update=True)

    assert first.created_count == 1
    assert second.updated_count == 1
    table_id = publisher.config.table_map[SKU_OVERVIEW]
    assert len(client.records[table_id]) == 1
    record = next(iter(client.records[table_id].values()))
    assert record["fields"]["均价"] == 5999.0


def test_cli_sync_all_routes_to_publisher(monkeypatch: Any, capsys: Any) -> None:
    @contextmanager
    def fake_session() -> Any:
        yield object()

    class FakePublisher:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def sync_all(self, **_kwargs: Any) -> PublishResult:
            return PublishResult(
                status="ok",
                category_code="TV",
                batch_id="m00_1",
                base_url="https://my.feishu.cn/base/test",
                scopes=[ScopeSyncResult(scope=SKU_OVERVIEW, status="dry_run", extracted_count=2)],
                message_cn="已同步小奥家电市场分析工作台。",
            )

    monkeypatch.setattr(catforge_publish, "SessionLocal", fake_session)
    monkeypatch.setattr(catforge_publish, "LarkCliBaseClient", lambda **_kwargs: object())
    monkeypatch.setattr(catforge_publish, "BaseWorkbenchPublisher", FakePublisher)

    code = catforge_publish.main(["base", "sync-all", "--batch-id", "latest", "--dry-run", "--format", "json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["batch_id"] == "m00_1"
    assert payload["scopes"][0]["scope"] == SKU_OVERVIEW


class _FakeExtractor:
    def __init__(self, *, records: dict[str, list[dict[str, Any]]]) -> None:
        self.records = records

    def resolve_batch_id(self, batch_id: str) -> str:
        return "m00_1" if batch_id == "latest" else batch_id

    def extract(self, scope: str, *, batch_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        rows = list(self.records.get(scope, []))
        return rows[:limit] if limit else rows

    def extract_analysis_batch(self, *, batch_id: str) -> list[dict[str, Any]]:
        return [
            {
                "batch_id": batch_id,
                "category_code": "TV",
                "product_category": "彩电",
                "source_batch_id": batch_id,
                "sync_status": "成功",
            }
        ]


def _publisher(*, client: InMemoryBaseClient, extractor: _FakeExtractor) -> BaseWorkbenchPublisher:
    return BaseWorkbenchPublisher(
        object(),  # type: ignore[arg-type]
        project_id="core3_mvp",
        category_code="TV",
        config=BaseWorkbenchConfig(base_token=client.base_token, table_map={}),
        client=client,
        extractor=extractor,  # type: ignore[arg-type]
    )
