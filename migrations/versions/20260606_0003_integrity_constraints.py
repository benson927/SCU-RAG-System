"""add document and index job integrity constraints

Revision ID: 20260606_0003
Revises: 20260605_0002
Create Date: 2026-06-06
"""
from typing import Sequence, Union

from alembic import op


revision: str = "20260606_0003"
down_revision: Union[str, None] = "20260605_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_document_versions_status",
        "document_versions",
        "status IN ('draft', 'published', 'archived')",
    )
    op.create_check_constraint(
        "ck_document_versions_size_positive",
        "document_versions",
        "size_bytes > 0",
    )
    op.create_check_constraint(
        "ck_document_versions_checksum_length",
        "document_versions",
        "length(checksum) = 64",
    )
    op.create_check_constraint(
        "ck_index_jobs_status",
        "index_jobs",
        "status IN ('pending', 'running', 'succeeded', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_index_jobs_status", "index_jobs", type_="check")
    op.drop_constraint("ck_document_versions_checksum_length", "document_versions", type_="check")
    op.drop_constraint("ck_document_versions_size_positive", "document_versions", type_="check")
    op.drop_constraint("ck_document_versions_status", "document_versions", type_="check")
