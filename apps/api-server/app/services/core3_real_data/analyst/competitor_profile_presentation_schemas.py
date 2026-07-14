"""Typed artifacts rendered from one immutable competitor-profile context."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CompetitorProfileBaseModel,
)


class CompetitorProfileQuestionAnswer(CompetitorProfileBaseModel):
    question_cn: str = Field(min_length=1)
    answer_cn: str = Field(min_length=1)
    supporting_products: list[str] = Field(default_factory=list)
    boundary_cn: str = Field(min_length=1)
    competitor_profile_version_id: str = Field(min_length=1)
    profile_result_hash: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)


class CompetitorProfilePresentationBundle(CompetitorProfileBaseModel):
    competitor_profile_version_id: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    profile_result_hash: str = Field(min_length=1)
    preview: bool
    short_answer: str = Field(min_length=1)
    feishu_card_payload: dict[str, Any]
    pm_report_title: str = Field(min_length=1)
    pm_report_markdown: str = Field(min_length=1)
    pm_report_delivery: dict[str, Any]
    evidence_report_title: str = Field(min_length=1)
    evidence_report_markdown: str = Field(min_length=1)
    evidence_report_delivery: dict[str, Any]
    qa_answers: list[CompetitorProfileQuestionAnswer] = Field(min_length=1)
    sellpoint_value_consumption: dict[str, Any]
    result_hash: str = Field(min_length=1)


__all__ = [
    "CompetitorProfilePresentationBundle",
    "CompetitorProfileQuestionAnswer",
]
