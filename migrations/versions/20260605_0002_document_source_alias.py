"""add stable source alias to documents

Revision ID: 20260605_0002
Revises: 20260605_0001
Create Date: 2026-06-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260605_0002"
down_revision: Union[str, None] = "20260605_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("source_alias", sa.String(length=255), nullable=True))
    op.execute(
        """
        WITH earliest AS (
            SELECT
                document_id,
                original_filename,
                ROW_NUMBER() OVER (PARTITION BY document_id ORDER BY created_at, id) AS row_num
            FROM document_versions
        ),
        chosen AS (
            SELECT document_id, original_filename
            FROM earliest
            WHERE row_num = 1
        ),
        named AS (
            SELECT
                document_id,
                original_filename,
                COUNT(*) OVER (PARTITION BY original_filename) AS filename_count
            FROM chosen
        )
        UPDATE documents AS document
        SET source_alias = CASE
            WHEN named.filename_count = 1 THEN LEFT(named.original_filename, 255)
            ELSE LEFT(named.original_filename, 240) || '-' || LEFT(document.id, 8)
        END
        FROM named
        WHERE named.document_id = document.id
        """
    )
    op.execute("UPDATE documents SET source_alias = id || '.pdf' WHERE source_alias IS NULL")
    op.alter_column("documents", "source_alias", existing_type=sa.String(length=255), nullable=False)
    op.create_unique_constraint("uq_documents_source_alias", "documents", ["source_alias"])


def downgrade() -> None:
    op.drop_constraint("uq_documents_source_alias", "documents", type_="unique")
    op.drop_column("documents", "source_alias")
