"""Memory-bounded full-category generation for sellpoint-value V5.1 drafts.

The parent process keeps only the authoritative SKU list and candidate-pool
hashes. Scope freezing and draft generation run in serial child chunks so a
full TV or AC run never retains every saved competitor/value graph in one
Python process.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import entities
from app.services.core3_real_data.analyst.competitor_profile_agent_snapshot_repository import (
    CompetitorProfileAgentSnapshotRepository,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SELLPOINT_VALUE_PROFILE_V5_1_RULE_VERSION,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_repositories import (
    SellpointValueProfileRepository,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_competitor_adapter import (
    SellpointValueCompetitorProfileAdapter,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_generation import (
    SellpointValueV51GenerationService,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_input_provider import (
    SPV_V5_1_PRODUCTION_METHOD_VERSIONS,
    SavedV5SellpointValueV51InputProvider,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_materializer_schemas import (
    SellpointValueV51VersionRequest,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_repository import (
    SellpointValueV51Repository,
)
from app.services.core3_real_data.constants import Core3CategoryCode
from app.services.core3_real_data.repositories import Core3RepositoryContext


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = (
            _run_scope_chunk(args)
            if args.command == "scope-chunk"
            else _run_generate_chunk(args)
            if args.command == "generate-chunk"
            else _run_batch(args)
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_code": exc.__class__.__name__,
                    "message": _safe_message(exc),
                },
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _run_batch(args: argparse.Namespace) -> dict[str, Any]:
    sku_codes = _authoritative_sku_codes(args)
    if not sku_codes:
        raise ValueError("saved V5 source contains no authoritative SKU")
    state_path = Path(args.state_file)
    if state_path.exists():
        request = SellpointValueV51VersionRequest.model_validate_json(
            state_path.read_text(encoding="utf-8")
        )
        _assert_request_matches_args(request, args, sku_codes)
        scope_reused = True
    else:
        fragments = [
            _run_child(
                "scope-chunk",
                args,
                sku_codes=chunk,
            )["request"]
            for chunk in _chunks(sku_codes, args.chunk_size)
        ]
        request = _merge_scope_fragments(fragments)
        _assert_request_matches_args(request, args, sku_codes)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            request.model_dump_json(indent=2),
            encoding="utf-8",
        )
        scope_reused = False

    if not args.enable_profile_write:
        return {
            "status": "scope_ready",
            "write_enabled": False,
            "scope_reused": scope_reused,
            "state_file": str(state_path),
            "profile_version": request.profile_version,
            "sku_count": len(request.expected_sku_codes),
            "candidate_hash_count": len(request.candidate_pool_hashes),
            "competitor_profile_version_id": (
                request.competitor_source.competitor_profile_version_id
            ),
        }

    _ensure_version(request, args.source_profile_version)
    unfinished = _unfinished_sku_codes(request)
    previously_generated_count = len(request.expected_sku_codes) - len(unfinished)
    if args.max_new_skus is not None:
        unfinished = unfinished[: args.max_new_skus]
    results = [
        _run_child(
            "generate-chunk",
            args,
            sku_codes=chunk,
        )
        for chunk in _chunks(unfinished, args.chunk_size)
    ]
    failed = [
        status
        for result in results
        for status in result["statuses"]
        if status["status"] == "failed"
    ]
    remaining = _unfinished_sku_codes(request)
    version = (
        _audit_version(request)
        if not failed and not remaining
        else _read_version(request)
    )
    return {
        "status": (
            "completed"
            if not failed and not remaining
            else "completed_with_failures"
            if failed
            else "checkpoint_completed"
        ),
        "write_enabled": True,
        "scope_reused": scope_reused,
        "state_file": str(state_path),
        "profile_version": request.profile_version,
        "requested_sku_count": len(request.expected_sku_codes),
        "previously_generated_count": previously_generated_count,
        "processed_in_this_run": len(unfinished),
        "failed_count": len(failed),
        "failed_statuses": failed,
        "remaining_count": len(remaining),
        "version": _version_summary(version),
    }


def _run_scope_chunk(args: argparse.Namespace) -> dict[str, Any]:
    with SessionLocal() as db:
        context = _context(db, args)
        provider = _provider(
            context,
            source_profile_version=args.source_profile_version,
        )
        request = provider.build_version_request(
            project_id=args.project_id,
            category_code=args.category_code,
            batch_id=args.batch_id,
            profile_version=args.profile_version,
            expected_sku_codes=args.sku_code,
            generated_by=args.generated_by,
        )
        return {
            "status": "scope_chunk_ready",
            "request": request.model_dump(mode="json"),
        }


def _run_generate_chunk(args: argparse.Namespace) -> dict[str, Any]:
    request = SellpointValueV51VersionRequest.model_validate_json(
        Path(args.state_file).read_text(encoding="utf-8")
    )
    requested = sorted(set(args.sku_code))
    if not set(requested).issubset(request.expected_sku_codes):
        raise ValueError("generation chunk exceeds the frozen authoritative scope")
    with SessionLocal() as db:
        context = _context(db, args)
        provider = _provider(
            context,
            source_profile_version=args.source_profile_version,
        )
        result = SellpointValueV51GenerationService(
            repository=SellpointValueV51Repository(context),
            input_provider=provider,
        ).generate_many(
            request,
            sku_codes=requested,
        )
        return {
            "status": "generation_chunk_completed",
            "generated_count": result.generated_count,
            "reused_count": result.reused_count,
            "failed_count": result.failed_count,
            "statuses": [
                row.model_dump(mode="json") for row in result.statuses
            ],
        }


def _run_child(
    command: str,
    args: argparse.Namespace,
    *,
    sku_codes: Sequence[str],
) -> dict[str, Any]:
    child_args = [
        sys.executable,
        "-m",
        "app.cli.sellpoint_value_v5_1_batch",
        command,
        "--project-id",
        args.project_id,
        "--category-code",
        args.category_code,
        "--batch-id",
        args.batch_id,
        "--profile-version",
        args.profile_version,
        "--source-profile-version",
        args.source_profile_version,
        "--generated-by",
        args.generated_by,
    ]
    if command == "generate-chunk":
        child_args.extend(("--state-file", args.state_file))
    for sku_code in sku_codes:
        child_args.extend(("--sku-code", sku_code))
    completed = subprocess.run(
        child_args,
        check=False,
        capture_output=True,
        text=True,
    )
    output = completed.stdout.strip()
    try:
        result = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{command} returned non-JSON output: {output[-300:]}"
        ) from exc
    if completed.returncode != 0 or result.get("status") == "error":
        raise RuntimeError(
            f"{command} failed: {result.get('message') or output[-300:]}"
        )
    return result


def _merge_scope_fragments(
    payloads: Sequence[dict[str, Any]],
) -> SellpointValueV51VersionRequest:
    if not payloads:
        raise ValueError("at least one scope fragment is required")
    fragments = [
        SellpointValueV51VersionRequest.model_validate(payload)
        for payload in payloads
    ]
    base = fragments[0]
    expected: list[str] = []
    candidate_hashes: dict[str, str] = {}
    for fragment in fragments:
        if (
            fragment.project_id != base.project_id
            or fragment.category_code != base.category_code
            or fragment.batch_id != base.batch_id
            or fragment.profile_version != base.profile_version
            or fragment.competitor_source != base.competitor_source
            or fragment.method_config != base.method_config
            or fragment.method_versions != base.method_versions
        ):
            raise ValueError("scope fragments do not share one immutable source")
        overlap = set(candidate_hashes) & set(fragment.candidate_pool_hashes)
        if overlap:
            raise ValueError("scope fragments contain duplicate SKU codes")
        expected.extend(fragment.expected_sku_codes)
        candidate_hashes.update(fragment.candidate_pool_hashes)
    expected = sorted(expected)
    return SellpointValueV51VersionRequest(
        project_id=base.project_id,
        category_code=base.category_code,
        batch_id=base.batch_id,
        profile_version=base.profile_version,
        competitor_source=base.competitor_source,
        expected_sku_codes=expected,
        candidate_pool_hashes=dict(sorted(candidate_hashes.items())),
        method_config=base.method_config,
        method_versions=dict(sorted(SPV_V5_1_PRODUCTION_METHOD_VERSIONS.items())),
        source_lineage=base.source_lineage,
        generated_by=base.generated_by,
    )


def _authoritative_sku_codes(args: argparse.Namespace) -> list[str]:
    with SessionLocal() as db:
        return list(
            db.execute(
                select(entities.Core3SkuSellpointValueProfile.sku_code)
                .where(
                    entities.Core3SkuSellpointValueProfile.project_id
                    == args.project_id
                )
                .where(
                    entities.Core3SkuSellpointValueProfile.category_code
                    == args.category_code
                )
                .where(
                    entities.Core3SkuSellpointValueProfile.batch_id == args.batch_id
                )
                .where(
                    entities.Core3SkuSellpointValueProfile.profile_version
                    == args.source_profile_version
                )
                .order_by(entities.Core3SkuSellpointValueProfile.sku_code)
            ).scalars()
        )


def _unfinished_sku_codes(
    request: SellpointValueV51VersionRequest,
) -> list[str]:
    with SessionLocal() as db:
        existing = set(
            db.execute(
                select(entities.Core3SkuSellpointValueProfile.sku_code)
                .where(
                    entities.Core3SkuSellpointValueProfile.project_id
                    == request.project_id
                )
                .where(
                    entities.Core3SkuSellpointValueProfile.category_code
                    == request.category_code
                )
                .where(
                    entities.Core3SkuSellpointValueProfile.batch_id
                    == request.batch_id
                )
                .where(
                    entities.Core3SkuSellpointValueProfile.profile_version
                    == request.profile_version
                )
                .where(
                    entities.Core3SkuSellpointValueProfile.rule_version
                    == SELLPOINT_VALUE_PROFILE_V5_1_RULE_VERSION
                )
            ).scalars()
        )
    return sorted(set(request.expected_sku_codes) - existing)


def _ensure_version(
    request: SellpointValueV51VersionRequest,
    source_profile_version: str,
) -> None:
    with SessionLocal() as db:
        context = Core3RepositoryContext(
            db=db,
            project_id=request.project_id,
            category_code=Core3CategoryCode(request.category_code),
        )
        SellpointValueV51GenerationService(
            repository=SellpointValueV51Repository(context),
            input_provider=_provider(
                context,
                source_profile_version=source_profile_version,
            ),
        ).ensure_version(request)


def _read_version(request: SellpointValueV51VersionRequest) -> dict[str, Any]:
    with SessionLocal() as db:
        context = Core3RepositoryContext(
            db=db,
            project_id=request.project_id,
            category_code=Core3CategoryCode(request.category_code),
        )
        version = SellpointValueV51Repository(context).get_version(
            batch_id=request.batch_id,
            profile_version=request.profile_version,
            rule_version=SELLPOINT_VALUE_PROFILE_V5_1_RULE_VERSION,
        )
        if version is None:
            raise RuntimeError("V5.1 version disappeared after batch generation")
        return version.model_dump(mode="json")


def _audit_version(request: SellpointValueV51VersionRequest) -> dict[str, Any]:
    with SessionLocal() as db:
        context = Core3RepositoryContext(
            db=db,
            project_id=request.project_id,
            category_code=Core3CategoryCode(request.category_code),
        )
        repository = SellpointValueV51Repository(context)
        version = repository.get_version(
            batch_id=request.batch_id,
            profile_version=request.profile_version,
            rule_version=SELLPOINT_VALUE_PROFILE_V5_1_RULE_VERSION,
        )
        if version is None:
            raise RuntimeError("V5.1 version disappeared before final audit")
        audited = repository.refresh_v5_1_version_progress(
            sellpoint_value_profile_version_id=(
                version.sellpoint_value_profile_version_id
            ),
            expected_sku_codes=request.expected_sku_codes,
            validate_readbacks=True,
        )
        db.commit()
        return audited.model_dump(mode="json")


def _version_summary(version: dict[str, Any]) -> dict[str, Any]:
    return {
        key: version.get(key)
        for key in (
            "sellpoint_value_profile_version_id",
            "profile_version",
            "release_status",
            "release_quality_status",
            "is_current",
            "sku_count",
            "ready_count",
            "review_required_count",
            "blocked_count",
            "failed_count",
            "conclusion_available_count",
            "partial_conclusion_count",
            "no_conclusion_count",
            "invalid_count",
            "integrity_error_count",
            "processing_status",
            "result_hash",
        )
    }


def _provider(
    context: Core3RepositoryContext,
    *,
    source_profile_version: str,
) -> SavedV5SellpointValueV51InputProvider:
    return SavedV5SellpointValueV51InputProvider(
        repository=SellpointValueProfileRepository(context),
        competitor_adapter=SellpointValueCompetitorProfileAdapter(
            CompetitorProfileAgentSnapshotRepository(context)
        ),
        source_profile_version=source_profile_version,
    )


def _context(db: Any, args: argparse.Namespace) -> Core3RepositoryContext:
    return Core3RepositoryContext(
        db=db,
        project_id=args.project_id,
        category_code=Core3CategoryCode(args.category_code),
    )


def _assert_request_matches_args(
    request: SellpointValueV51VersionRequest,
    args: argparse.Namespace,
    sku_codes: Sequence[str],
) -> None:
    if (
        request.project_id != args.project_id
        or request.category_code != args.category_code
        or request.batch_id != args.batch_id
        or request.profile_version != args.profile_version
        or request.generated_by != args.generated_by
        or request.expected_sku_codes != sorted(set(sku_codes))
    ):
        raise ValueError("saved scope manifest does not match this batch request")


def _chunks(values: Sequence[str], size: int) -> list[list[str]]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    return [
        list(values[index : index + size])
        for index in range(0, len(values), size)
    ]


def _safe_message(exc: Exception) -> str:
    return (" ".join(str(exc).split()) or exc.__class__.__name__)[:500]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    _add_common_args(run)
    run.add_argument("--state-file", required=True)
    run.add_argument("--chunk-size", type=int, default=25)
    run.add_argument("--max-new-skus", type=int)
    run.add_argument("--enable-profile-write", action="store_true")

    scope = subparsers.add_parser("scope-chunk")
    _add_common_args(scope)
    scope.add_argument("--sku-code", action="append", required=True)

    generate = subparsers.add_parser("generate-chunk")
    _add_common_args(generate)
    generate.add_argument("--state-file", required=True)
    generate.add_argument("--sku-code", action="append", required=True)
    return parser


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--category-code", choices=("TV", "AC"), required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--profile-version", required=True)
    parser.add_argument("--source-profile-version", required=True)
    parser.add_argument("--generated-by", required=True)


if __name__ == "__main__":
    raise SystemExit(main())
