from sqlalchemy.dialects import postgresql

from app.services.core3_real_data.api_repositories import Core3RealDataApiRepository
from app.services.core3_real_data.repositories import Core3RepositoryContext


def test_target_report_summary_query_excludes_heavy_payload_columns():
    repository = Core3RealDataApiRepository(Core3RepositoryContext(db=None, project_id="project-1"))

    sql = str(
        repository._target_report_summary_stmt(batch_id="batch-1").compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "core3_target_report_payload.short_evidence_map_json" not in sql
    assert "core3_target_report_payload.export_payload_json" not in sql
    assert "core3_target_report_payload.sop_trace_json" not in sql
    assert "core3_target_report_payload.evidence_matrix_json" not in sql
    assert "core3_target_report_payload.target_sku_code" in sql
    assert "core3_target_report_payload.core_competitors_json" in sql
