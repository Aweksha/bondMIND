"""fractional curve tenors

Revision ID: 7e19f97d7ab6
Revises: cd1b752ac1d9
Create Date: 2026-11-07 15:53:32.542289
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7e19f97d7ab6"
down_revision: str | None = "cd1b752ac1d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Batch mode: a plain ALTER on PostgreSQL, a copy-and-swap on SQLite.
    with op.batch_alter_table("curve_points") as batch:
        batch.alter_column(
            "tenor_months",
            existing_type=sa.INTEGER(),
            type_=sa.Numeric(precision=6, scale=2),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("curve_points") as batch:
        batch.alter_column(
            "tenor_months",
            existing_type=sa.Numeric(precision=6, scale=2),
            type_=sa.INTEGER(),
            existing_nullable=False,
        )
