"""Recoverable jobs and evaluation records."""
from alembic import op
import sqlalchemy as sa

revision = "0007_jobs_evaluation"
down_revision = "0006_story_graph"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("jobs", sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("job_type", sa.String(40), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="queued"), sa.Column("progress", sa.JSON(), nullable=False, server_default="{}"), sa.Column("input_snapshot", sa.JSON(), nullable=False, server_default="{}"), sa.Column("output", sa.JSON(), nullable=False, server_default="{}"), sa.Column("error", sa.Text()), sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.create_table("evaluation_cases", sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE")), sa.Column("name", sa.String(200), nullable=False), sa.Column("task_type", sa.String(40), nullable=False), sa.Column("input_data", sa.JSON(), nullable=False, server_default="{}"), sa.Column("expected", sa.JSON(), nullable=False, server_default="{}"), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("evaluation_runs", sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE")), sa.Column("case_id", sa.String(36), sa.ForeignKey("evaluation_cases.id", ondelete="CASCADE"), nullable=False), sa.Column("provider_id", sa.String(36)), sa.Column("model", sa.String(200)), sa.Column("prompt_version", sa.String(200)), sa.Column("result", sa.JSON(), nullable=False, server_default="{}"), sa.Column("metrics", sa.JSON(), nullable=False, server_default="{}"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))

def downgrade():
    op.drop_table("evaluation_runs"); op.drop_table("evaluation_cases"); op.drop_table("jobs")
