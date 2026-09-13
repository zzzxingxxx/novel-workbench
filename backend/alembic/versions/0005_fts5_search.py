"""SQLite FTS5 project search index"""

from alembic import op
import sqlalchemy as sa

revision = "0005_fts5_search"
down_revision = "0004_context_tools"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    bind.execute(
        sa.text(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS search_index_fts USING fts5(
                project_id UNINDEXED,
                source_type UNINDEXED,
                source_id UNINDEXED,
                volume_id UNINDEXED,
                chapter_id UNINDEXED,
                title,
                body,
                aliases,
                tags,
                tokenize='unicode61'
            )
            """
        )
    )
    bind.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS search_index_meta (
                project_id TEXT PRIMARY KEY,
                source_stamp TEXT NOT NULL,
                indexed_at TEXT NOT NULL
            )
            """
        )
    )
    op.add_column("ai_messages", sa.Column("retrieval_query", sa.String(500)))
    op.add_column("ai_messages", sa.Column("retrieval_limit", sa.Integer(), nullable=False, server_default="8"))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        bind.execute(sa.text("DROP TABLE IF EXISTS search_index_meta"))
        bind.execute(sa.text("DROP TABLE IF EXISTS search_index_fts"))
    op.drop_column("ai_messages", "retrieval_limit")
    op.drop_column("ai_messages", "retrieval_query")
