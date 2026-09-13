"""versioned system prompt templates and session snapshots"""

from alembic import op
import sqlalchemy as sa

revision = "0003_prompt_system"
down_revision = "0002_ai_provider_sse"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("owner_id", sa.String(36)),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active_version_id", sa.String(36), sa.ForeignKey("prompt_versions.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_prompt_templates_project_id", "prompt_templates", ["project_id"])
    op.create_index("ix_prompt_templates_scope", "prompt_templates", ["scope"])
    op.create_index("ix_prompt_templates_owner_id", "prompt_templates", ["owner_id"])
    op.create_index("ix_prompt_templates_active_version_id", "prompt_templates", ["active_version_id"])
    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("template_id", sa.String(36), sa.ForeignKey("prompt_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("variables", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(120)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("template_id", "version", name="uq_prompt_version"),
    )
    op.create_index("ix_prompt_versions_template_id", "prompt_versions", ["template_id"])
    op.add_column("ai_sessions", sa.Column("agent_id", sa.String(36)))
    op.add_column("ai_sessions", sa.Column("workflow_id", sa.String(36)))
    op.add_column("ai_sessions", sa.Column("prompt_variables", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("ai_sessions", sa.Column("prompt_version_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("ai_sessions", sa.Column("prompt_snapshot", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("ai_sessions", sa.Column("prompt_digest", sa.String(64)))
    op.create_index("ix_ai_sessions_agent_id", "ai_sessions", ["agent_id"])
    op.create_index("ix_ai_sessions_workflow_id", "ai_sessions", ["workflow_id"])
    op.create_index("ix_ai_sessions_prompt_digest", "ai_sessions", ["prompt_digest"])


def downgrade() -> None:
    op.drop_index("ix_ai_sessions_prompt_digest", table_name="ai_sessions")
    op.drop_index("ix_ai_sessions_workflow_id", table_name="ai_sessions")
    op.drop_index("ix_ai_sessions_agent_id", table_name="ai_sessions")
    for column in ("prompt_digest", "prompt_snapshot", "prompt_version_ids", "prompt_variables", "workflow_id", "agent_id"):
        op.drop_column("ai_sessions", column)
    op.drop_index("ix_prompt_versions_template_id", table_name="prompt_versions")
    op.drop_table("prompt_versions")
    op.drop_index("ix_prompt_templates_active_version_id", table_name="prompt_templates")
    op.drop_index("ix_prompt_templates_owner_id", table_name="prompt_templates")
    op.drop_index("ix_prompt_templates_scope", table_name="prompt_templates")
    op.drop_index("ix_prompt_templates_project_id", table_name="prompt_templates")
    op.drop_table("prompt_templates")
