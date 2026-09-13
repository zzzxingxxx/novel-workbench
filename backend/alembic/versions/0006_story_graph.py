"""Story graph, entity history and operation metadata."""

from alembic import op
import sqlalchemy as sa

revision = "0006_story_graph"
down_revision = "0005_fts5_search"
branch_labels = None
depends_on = None


def _table(name, columns, constraints=()):
    op.create_table(name, *columns, *constraints)


def upgrade() -> None:
    op.add_column("entities", sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("operations", sa.Column("target_version_hash", sa.String(64)))
    op.add_column("operations", sa.Column("diff", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("operations", sa.Column("permission", sa.String(30), nullable=False, server_default="approval_required"))
    op.add_column("operations", sa.Column("undo_operation_id", sa.String(36)))
    _table("entity_source_links", [
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", sa.String(36), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False), sa.Column("chapter_id", sa.String(36), sa.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False), sa.Column("evidence", sa.Text(), nullable=False, server_default=""), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("entity_id", "chapter_id", name="uq_entity_source_chapter")
    ])
    _table("entity_revisions", [sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("entity_id", sa.String(36), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False), sa.Column("snapshot", sa.JSON(), nullable=False), sa.Column("source", sa.String(30), nullable=False, server_default="user"), sa.Column("operation_id", sa.String(36)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)])
    _table("timeline_events", [sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("title", sa.String(200), nullable=False), sa.Column("description", sa.Text(), nullable=False, server_default=""), sa.Column("absolute_time", sa.String(100)), sa.Column("relative_order", sa.Integer()), sa.Column("time_status", sa.String(20), nullable=False, server_default="unknown"), sa.Column("chapter_ids", sa.JSON(), nullable=False, server_default="[]"), sa.Column("entity_ids", sa.JSON(), nullable=False, server_default="[]"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)])
    _table("story_branches", [sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("parent_id", sa.String(36), sa.ForeignKey("story_branches.id", ondelete="SET NULL")), sa.Column("name", sa.String(200), nullable=False), sa.Column("trigger_condition", sa.Text(), nullable=False, server_default=""), sa.Column("chapter_ids", sa.JSON(), nullable=False, server_default="[]"), sa.Column("status", sa.String(30), nullable=False, server_default="active"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)])
    _table("foreshadows", [sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("title", sa.String(200), nullable=False), sa.Column("description", sa.Text(), nullable=False, server_default=""), sa.Column("status", sa.String(20), nullable=False, server_default="draft"), sa.Column("planted_chapter_ids", sa.JSON(), nullable=False, server_default="[]"), sa.Column("resolved_chapter_ids", sa.JSON(), nullable=False, server_default="[]"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)])
    _table("foreshadow_links", [sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("foreshadow_id", sa.String(36), sa.ForeignKey("foreshadows.id", ondelete="CASCADE"), nullable=False), sa.Column("source_type", sa.String(20), nullable=False), sa.Column("source_id", sa.String(36), nullable=False), sa.Column("evidence", sa.Text(), nullable=False, server_default=""), sa.Column("link_kind", sa.String(20), nullable=False, server_default="evidence"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)])


def downgrade() -> None:
    for name in ("foreshadow_links", "foreshadows", "story_branches", "timeline_events", "entity_revisions", "entity_source_links"):
        op.drop_table(name)
    for name in ("undo_operation_id", "permission", "diff", "target_version_hash"):
        op.drop_column("operations", name)
    op.drop_column("entities", "tags")
