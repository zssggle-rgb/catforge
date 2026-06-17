"""core3 real data dimension ontology calibration

Revision ID: 0028_core3_dimension_ontology
Revises: 0027_core3_sales_recon
Create Date: 2026-06-15
"""

from alembic import op

from app.models.entities import (
    Core3DimensionCalibrationIssue,
    Core3DimensionCandidateSnapshot,
    Core3DimensionDefinition,
    Core3DimensionEvidenceAnchor,
    Core3DimensionMappingRule,
    Core3DimensionOntologyVersion,
)

revision = "0028_core3_dimension_ontology"
down_revision = "0027_core3_sales_recon"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (
        Core3DimensionOntologyVersion.__table__,
        Core3DimensionDefinition.__table__,
        Core3DimensionEvidenceAnchor.__table__,
        Core3DimensionMappingRule.__table__,
        Core3DimensionCandidateSnapshot.__table__,
        Core3DimensionCalibrationIssue.__table__,
    ):
        table.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for table in (
        Core3DimensionCalibrationIssue.__table__,
        Core3DimensionCandidateSnapshot.__table__,
        Core3DimensionMappingRule.__table__,
        Core3DimensionEvidenceAnchor.__table__,
        Core3DimensionDefinition.__table__,
        Core3DimensionOntologyVersion.__table__,
    ):
        table.drop(op.get_bind(), checkfirst=True)
