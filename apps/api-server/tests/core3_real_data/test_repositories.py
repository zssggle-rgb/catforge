from datetime import timezone

import pytest

from app.services.core3_real_data.constants import Core3CategoryCode
from app.services.core3_real_data.repositories import (
    CORE3_RAW_SOURCE_TABLES,
    Core3BaseRepository,
    Core3RepositoryContext,
    RawSourceMutationNotAllowed,
    RawSourceReadOnlyGuard,
    RawSourceReadOnlyMixin,
)


class FakeSession:
    pass


def test_repository_context_requires_project_id_and_normalizes_category():
    context = Core3RepositoryContext(db=FakeSession(), project_id="project-001", category_code="TV")

    assert context.project_id == "project-001"
    assert context.category_code == Core3CategoryCode.TV

    with pytest.raises(ValueError, match="project_id"):
        Core3RepositoryContext(db=FakeSession(), project_id=" ")


def test_base_repository_exposes_context_and_utility_methods():
    repo = Core3BaseRepository(Core3RepositoryContext(db=FakeSession(), project_id="project-001"))

    assert isinstance(repo.db, FakeSession)
    assert repo.project_id == "project-001"
    assert repo.category_code == Core3CategoryCode.TV
    assert repo.pagination(limit=0, offset=-10, max_limit=50) == (1, 0)
    assert repo.pagination(limit=500, offset=20, max_limit=50) == (50, 20)

    audit_fields = repo.audit_fields(actor="pytest")
    assert audit_fields["created_by"] == "pytest"
    assert audit_fields["updated_by"] == "pytest"
    assert audit_fields["created_at"].tzinfo == timezone.utc
    assert audit_fields["updated_at"].tzinfo == timezone.utc


def test_raw_source_guard_accepts_known_source_tables_only():
    assert CORE3_RAW_SOURCE_TABLES == (
        "week_sales_data",
        "attribute_data",
        "selling_points_data",
        "comment_data",
    )
    assert RawSourceReadOnlyGuard.ensure_raw_source_table("week_sales_data") == "week_sales_data"

    with pytest.raises(ValueError, match="unknown raw source table"):
        RawSourceReadOnlyGuard.ensure_raw_source_table("core3_clean_sku")


def test_raw_source_guard_rejects_mutation_method_names():
    assert RawSourceReadOnlyGuard.ensure_select_method("select_week_sales_data") == "select_week_sales_data"
    assert RawSourceReadOnlyGuard.ensure_select_method("count_comments") == "count_comments"

    for method_name in ["insert_week_sales_data", "update_comment_data", "delete_attribute_data", "save_raw_row"]:
        with pytest.raises(RawSourceMutationNotAllowed, match="not read-only"):
            RawSourceReadOnlyGuard.ensure_select_method(method_name)


def test_raw_source_guard_rejects_mutation_sql():
    assert RawSourceReadOnlyGuard.ensure_read_only_sql("select * from week_sales_data") == "select * from week_sales_data"
    assert RawSourceReadOnlyGuard.ensure_read_only_sql("WITH rows AS (SELECT 1) SELECT * FROM rows")

    for sql in [
        "insert into week_sales_data values (1)",
        "update comment_data set sentiment = 'positive'",
        "delete from attribute_data",
        "drop table selling_points_data",
    ]:
        with pytest.raises(RawSourceMutationNotAllowed, match="read-only|must start"):
            RawSourceReadOnlyGuard.ensure_read_only_sql(sql)


def test_raw_source_guard_can_inspect_repository_interface():
    class ReadOnlyRepo:
        def select_week_sales_data(self):
            return []

        def count_comment_data(self):
            return 0

    class MutatingRepo:
        def select_week_sales_data(self):
            return []

        def update_week_sales_data(self):
            return None

    RawSourceReadOnlyGuard.assert_repository_interface_read_only(ReadOnlyRepo())

    with pytest.raises(RawSourceMutationNotAllowed, match="not read-only"):
        RawSourceReadOnlyGuard.assert_repository_interface_read_only(MutatingRepo())


def test_raw_source_read_only_mixin_delegates_to_guard():
    class RepoWithGuard(RawSourceReadOnlyMixin):
        pass

    repo = RepoWithGuard()

    assert repo.ensure_raw_source_table("comment_data") == "comment_data"
    with pytest.raises(RawSourceMutationNotAllowed):
        repo.ensure_select_method("delete_comment_data")

