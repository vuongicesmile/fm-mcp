"""Import all EPIC 3 models so Alembic registers their metadata."""

from fm_mcp.domain.models.workflow import (
    ApprovalAction,
    ApprovalAssignment,
    ApprovalStep,
    Attachment,
    AuditLog,
    EscalationRule,
    FMRequest,
    Notification,
    NotificationTemplate,
    Reminder,
    RequestStatusHistory,
    Risk,
    RiskAssessment,
    WorkflowDefinition,
    WorkflowStep,
)

__all__ = [
    "ApprovalAction", "ApprovalAssignment", "ApprovalStep", "Attachment", "AuditLog",
    "EscalationRule", "FMRequest", "Notification", "NotificationTemplate", "Reminder",
    "RequestStatusHistory", "Risk", "RiskAssessment", "WorkflowDefinition", "WorkflowStep",
]
