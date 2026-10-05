"""Scope the rebuildable read cache to the configured contract deployment.

Revision ID: 20261002_01
Revises: eec8b3f2b10e
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20261002_01"
down_revision = "eec8b3f2b10e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sync_cursor", sa.Column("contract_address", sa.String(length=42), nullable=True))
    op.add_column("loans", sa.Column("principal_claimed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("loans", "principal_claimed", server_default=None)


def downgrade() -> None:
    op.drop_column("loans", "principal_claimed")
    op.drop_column("sync_cursor", "contract_address")
