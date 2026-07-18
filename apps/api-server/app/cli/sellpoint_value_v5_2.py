"""Generate source-grounded sellpoint-value V5.2 drafts.

This command is intentionally write-gated.  Without
``--enable-profile-write`` it only freezes and validates the requested scope.
It never reviews, publishes, or changes the current version.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from typing import Any

from app.core.database import SessionLocal
from app.services.core3_real_data.analyst.competitor_profile_agent_snapshot_repository import (
    CompetitorProfileAgentSnapshotRepository,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_repositories import (
    SellpointValueProfileRepository,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_competitor_adapter import (
    SellpointValueCompetitorProfileAdapter,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_input_provider import (
    SavedV5SellpointValueV51InputProvider,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_claim_reader import (
    M04CSourceSellpointReader,
    SqlAlchemyM04CSourceSellpointRepository,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_generation import (
    SellpointValueV52GenerationService,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_input_provider import (
    SavedV5SellpointValueV52InputProvider,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_repository import (
    SellpointValueV52Repository,
)
from app.services.core3_real_data.constants import Core3CategoryCode
from app.services.core3_real_data.repositories import Core3RepositoryContext


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = _run(args)
    except Exception as exc:
        payload = {
            "status": "error",
            "error_code": exc.__class__.__name__,
            "message": _safe_message(exc),
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 1
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def _run(args: argparse.Namespace) -> dict[str, Any]:
    sku_codes = sorted(
        {
            str(sku_code).strip().upper()
            for sku_code in args.sku_code
            if str(sku_code).strip()
        }
    )
    if not sku_codes:
        raise ValueError("at least one SKU code is required")
    with SessionLocal() as db:
        context = Core3RepositoryContext(
            db=db,
            project_id=args.project_id,
            category_code=Core3CategoryCode(args.category_code),
        )
        provider = _provider(
            context,
            source_profile_version=args.source_profile_version,
        )
        request = provider.build_version_request(
            project_id=args.project_id,
            category_code=args.category_code,
            batch_id=args.batch_id,
            profile_version=args.profile_version,
            expected_sku_codes=sku_codes,
            generated_by=args.generated_by,
        )
        scope = {
            "profile_version": request.base.profile_version,
            "source_profile_version": args.source_profile_version,
            "sku_count": len(request.base.expected_sku_codes),
            "sku_codes": request.base.expected_sku_codes,
            "competitor_profile_version_id": (
                request.base.competitor_source.competitor_profile_version_id
            ),
            "m04c_source_hash_count": len(request.source_hashes_by_sku),
        }
        if not args.enable_profile_write:
            return {
                "status": "scope_ready",
                "write_enabled": False,
                **scope,
            }
        result = SellpointValueV52GenerationService(
            repository=SellpointValueV52Repository(context),
            input_provider=provider,
        ).generate_many(request, sku_codes=sku_codes)
        return {
            "status": (
                "completed"
                if result.failed_count == 0
                else "completed_with_failures"
            ),
            "write_enabled": True,
            **scope,
            "generated_count": result.generated_count,
            "reused_count": result.reused_count,
            "failed_count": result.failed_count,
            "statuses": [
                row.model_dump(mode="json") for row in result.statuses
            ],
            "version": {
                "sellpoint_value_profile_version_id": (
                    result.version.sellpoint_value_profile_version_id
                ),
                "release_status": result.version.release_status,
                "is_current": result.version.is_current,
                "processing_status": result.version.processing_status,
                "result_hash": result.version.result_hash,
            },
        }


def _provider(
    context: Core3RepositoryContext,
    *,
    source_profile_version: str,
) -> SavedV5SellpointValueV52InputProvider:
    base = SavedV5SellpointValueV51InputProvider(
        repository=SellpointValueProfileRepository(context),
        competitor_adapter=SellpointValueCompetitorProfileAdapter(
            CompetitorProfileAgentSnapshotRepository(context)
        ),
        source_profile_version=source_profile_version,
    )
    return SavedV5SellpointValueV52InputProvider(
        base_provider=base,
        source_sellpoint_reader=M04CSourceSellpointReader(
            SqlAlchemyM04CSourceSellpointRepository(
                context.db,
                project_id=context.project_id,
                category_code=context.category_code.value,
            )
        ),
    )


def _safe_message(exc: Exception) -> str:
    return (" ".join(str(exc).split()) or exc.__class__.__name__)[:500]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--category-code", choices=("TV", "AC"), required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--profile-version", required=True)
    parser.add_argument("--source-profile-version", required=True)
    parser.add_argument("--generated-by", required=True)
    parser.add_argument("--sku-code", action="append", required=True)
    parser.add_argument("--enable-profile-write", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
