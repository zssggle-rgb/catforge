from typing import Any

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category_code: str = "TV"
    description: str | None = None


class ProjectOut(BaseModel):
    project_id: str
    name: str
    category_code: str
    description: str | None = None
    version: str
    status: str

    model_config = {"from_attributes": True}


class SourceFileOut(BaseModel):
    source_file_id: str
    project_id: str
    category_code: str
    file_name: str
    file_type: str
    storage_path: str
    status: str
    row_count: int

    model_config = {"from_attributes": True}


class ImportRequest(BaseModel):
    source_file_id: str | None = None
    file_path: str | None = None
    file_type: str | None = None


class ImportOut(BaseModel):
    import_batch_id: str
    source_file_id: str
    file_type: str
    status: str
    row_count: int
    error_count: int

    model_config = {"from_attributes": True}


class PipelineOut(BaseModel):
    step: str
    status: str = "completed"
    counts: dict[str, int | float] = Field(default_factory=dict)
    message: str = "处理完成"


class DataQualityOut(BaseModel):
    project_id: str
    summary: dict[str, Any]
    issues: list[dict[str, Any]]


class ReviewDecision(BaseModel):
    decision: str = Field(pattern="^(approved|rejected|edited)$")
    reviewer: str = "system"
    decision_payload: dict[str, Any] | None = None


class ExportRequest(BaseModel):
    version: str = "0.1.0"


class ExportOut(BaseModel):
    package_id: str
    package_path: str
    files: list[str]
    status: str
    message: str

