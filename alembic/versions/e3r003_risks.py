"""Create risk register and assessment tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e3r003_risks"
down_revision = "e3a002_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("fm_risks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("risk_code", sa.String(50), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True)), sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False), sa.Column("category", sa.String(100)),
        sa.Column("owner_id", sa.String(100), nullable=False), sa.Column("status", sa.String(30), nullable=False, server_default="open"),
        sa.Column("mitigation_plan", sa.Text()), sa.Column("review_date", sa.Date()), sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["request_id"], ["fm_requests.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("risk_code", name="uq_fm_risks_risk_code"),
        sa.CheckConstraint("status IN ('open', 'mitigating', 'mitigated', 'accepted', 'closed')", name="ck_fm_risks_status"))
    op.create_index("ix_fm_risks_status_review_date", "fm_risks", ["status", "review_date"])
    op.create_index("ix_fm_risks_owner_status", "fm_risks", ["owner_id", "status"])
    op.create_table("fm_risk_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("risk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("likelihood", sa.SmallInteger(), nullable=False), sa.Column("impact", sa.SmallInteger(), nullable=False),
        sa.Column("risk_score", sa.SmallInteger(), nullable=False), sa.Column("assessment_type", sa.String(30), nullable=False),
        sa.Column("notes", sa.Text()), sa.Column("assessed_by", sa.String(100), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["risk_id"], ["fm_risks.id"], ondelete="CASCADE"),
        sa.CheckConstraint("likelihood BETWEEN 1 AND 5", name="ck_fm_risk_assessments_likelihood"),
        sa.CheckConstraint("impact BETWEEN 1 AND 5", name="ck_fm_risk_assessments_impact"),
        sa.CheckConstraint("risk_score BETWEEN 1 AND 25", name="ck_fm_risk_assessments_score"))
    op.create_index("ix_fm_risk_assessments_risk_assessed_at", "fm_risk_assessments", ["risk_id", "assessed_at"])


def downgrade() -> None:
    op.drop_table("fm_risk_assessments")
    op.drop_table("fm_risks")
