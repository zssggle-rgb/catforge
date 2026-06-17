"""clean legacy market profile constraints

Revision ID: 0025_market_profile_legacy_fk
Revises: 0024_core3_pipeline_governance
Create Date: 2026-06-14
"""

from alembic import op
import sqlalchemy as sa

revision = "0025_market_profile_legacy_fk"
down_revision = "0024_core3_pipeline_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    if not inspector.has_table("core3_sku_market_profile"):
        return

    bind.execute(
        sa.text(
            """
            DO $$
            DECLARE
                constraint_name text;
            BEGIN
                FOR constraint_name IN
                    SELECT con.conname
                    FROM pg_constraint con
                    JOIN pg_class rel ON rel.oid = con.conrelid
                    JOIN pg_class ref ON ref.oid = con.confrelid
                    WHERE con.contype = 'f'
                      AND rel.relname = 'core3_sku_market_profile'
                      AND ref.relname = 'core3_pipeline_run'
                LOOP
                    EXECUTE format(
                        'ALTER TABLE core3_sku_market_profile DROP CONSTRAINT IF EXISTS %I',
                        constraint_name
                    );
                END LOOP;
            END $$;
            """
        )
    )
    bind.execute(
        sa.text(
            """
            ALTER TABLE core3_sku_market_profile
            DROP CONSTRAINT IF EXISTS uq_core3_market_profile_run_sku
            """
        )
    )


def downgrade() -> None:
    # The current v2 market-profile pipeline only treats run_id as trace metadata
    # on this compatibility table. Recreating the old MVP foreign key would break
    # v2 reruns, so downgrade intentionally leaves the column unconstrained.
    return
