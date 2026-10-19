"""Store immutable request context supplied through MCP."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e3e006_request_context"
down_revision = "e3s005_supporting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fm_requests",
        sa.Column("context", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("fm_requests", "context")
