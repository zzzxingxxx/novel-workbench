"""auditable context packages and tool metadata"""

from alembic import op
import sqlalchemy as sa

revision = "0004_context_tools"
down_revision = "0003_prompt_system"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_messages", sa.Column("context_package", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("ai_messages", sa.Column("context_digest", sa.String(64)))
    op.add_column("ai_messages", sa.Column("context_tokens", sa.Integer()))
    op.add_column("ai_messages", sa.Column("context_budget", sa.Integer(), nullable=False, server_default="6000"))
    op.create_index("ix_ai_messages_context_digest", "ai_messages", ["context_digest"])


def downgrade() -> None:
    op.drop_index("ix_ai_messages_context_digest", table_name="ai_messages")
    op.drop_column("ai_messages", "context_budget")
    op.drop_column("ai_messages", "context_tokens")
    op.drop_column("ai_messages", "context_digest")
    op.drop_column("ai_messages", "context_package")
