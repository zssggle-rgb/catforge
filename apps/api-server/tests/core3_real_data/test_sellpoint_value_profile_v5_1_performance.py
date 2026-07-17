from __future__ import annotations

from decimal import Decimal
from time import perf_counter
import tracemalloc
from typing import Any

import pytest
from sqlalchemy import event

from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_candidate_pools import (
    build_sellpoint_value_candidate_pools,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_consumer import (
    SellpointValueV51ConsumerReadRequest,
    SellpointValueV51ConsumerReader,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_generation import (
    SellpointValueV51GenerationService,
)
from tests.core3_real_data.test_sellpoint_value_profile_v5_1_candidate_pools import (
    _candidate as _competitor_candidate,
    _source as _competitor_source,
)
from tests.core3_real_data.test_sellpoint_value_profile_v5_1_materialization import (
    FixtureProvider,
    _materialization_input,
    _repository,
    _request,
    session as _materialization_session,
)


@pytest.fixture
def performance_session():
    fixture = _materialization_session.__wrapped__()
    db = next(fixture)
    try:
        yield db
    finally:
        try:
            next(fixture)
        except StopIteration:
            pass


def _maximum_candidate_source():
    selected_ranks = {1: 2, 3: 1, 4: 3}
    candidates = [
        _competitor_candidate(
            rank,
            selected_rank=selected_ranks.get(rank),
            price=Decimal("5000") + rank,
            weekly_sales=Decimal("40") + rank,
        )
        for rank in range(1, 21)
    ]
    competitor_source = _competitor_source().model_copy(
        update={
            "candidates": candidates,
            "priority_order": ["TV-C03", "TV-C01", "TV-C04"],
            "source_result_hash": "profile-hash-max-20",
        }
    )
    references: list[dict[str, Any]] = []
    for rank in range(1, 52):
        sku_code = f"TV-C{rank:02d}" if rank <= 20 else f"TV-R{rank:02d}"
        references.append(
            {
                "reference_sku_code": sku_code,
                "brand_name": f"参照品牌-{rank % 9}",
                "model_name": f"参照型号-{rank}",
                "reference_purposes": ["same_size_market"],
                "market_summary": {
                    "price_wavg": 4800 + rank,
                    "avg_weekly_sales_volume": 30 + rank,
                },
                "source_hashes": {"M07": f"market-hash-{rank}"},
            }
        )
    pools = build_sellpoint_value_candidate_pools(
        competitor_source=competitor_source,
        analysis_reference_records=references,
    )
    return _materialization_input(profile_version="spv-v51-max-20-51").model_copy(
        update={
            "competitor_source": competitor_source,
            "candidate_pools": pools,
        }
    )


def test_maximum_20_competitor_51_reference_profile_read_is_bounded(
    performance_session,
) -> None:
    source = _maximum_candidate_source()
    repository = _repository(performance_session)
    readback = SellpointValueV51GenerationService(
        repository=repository,
        input_provider=FixtureProvider({source.target.sku_code: source}),
    ).generate_draft(_request(source), sku_code=source.target.sku_code)
    version_id = readback.persisted.version.sellpoint_value_profile_version_id
    engine = performance_session.get_bind()
    select_statements: list[str] = []

    def count_selects(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    event.listen(engine, "before_cursor_execute", count_selects)
    tracemalloc.start()
    started = perf_counter()
    try:
        consumed = SellpointValueV51ConsumerReader(repository).read(
            SellpointValueV51ConsumerReadRequest(
                project_id=source.project_id,
                category_code=source.category_code,
                batch_id=source.batch_id,
                access_mode="preview",
                sku_code=source.target.sku_code,
                profile_version=source.profile_version,
                sellpoint_value_profile_version_id=version_id,
            )
        )
        elapsed_seconds = perf_counter() - started
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        event.remove(engine, "before_cursor_execute", count_selects)

    assert consumed.status == "available"
    assert consumed.readback is not None
    assert len(consumed.readback.profile.candidate_pools.formal_competitors) == 20
    assert len(consumed.readback.profile.candidate_pools.analysis_references) == 51
    assert len(select_statements) <= 8
    assert all("question_analyses_json" not in row for row in select_statements[:2])
    assert elapsed_seconds < 2
    assert peak_bytes < 32 * 1024 * 1024
