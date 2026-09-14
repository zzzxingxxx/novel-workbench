"""Request diagnostics and AI latency metadata."""

from alembic import op
import sqlalchemy as sa

revision = "0008_observability"
down_revision = "0007_jobs_evaluation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_messages", sa.Column("latency_ms", sa.Integer()))
    op.add_column("ai_messages", sa.Column("provider_id_used", sa.String(36)))
    op.add_column("ai_messages", sa.Column("model_used", sa.String(200)))
    op.create_index("ix_ai_messages_provider_id_used", "ai_messages", ["provider_id_used"])
    op.create_table(
        "request_metrics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(36), nullable=False, unique=True),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.String(300), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_request_metrics_request_id", "request_metrics", ["request_id"])
    op.create_index("ix_request_metrics_path", "request_metrics", ["path"])
    op.create_index("ix_request_metrics_created_at", "request_metrics", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_request_metrics_created_at", table_name="request_metrics")
    op.drop_index("ix_request_metrics_path", table_name="request_metrics")
    op.drop_index("ix_request_metrics_request_id", table_name="request_metrics")
    op.drop_table("request_metrics")
    op.drop_index("ix_ai_messages_provider_id_used", table_name="ai_messages")
    op.drop_column("ai_messages", "model_used")
    op.drop_column("ai_messages", "provider_id_used")
    op.drop_column("ai_messages", "latency_ms")
