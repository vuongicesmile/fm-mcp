"""Approval MCP tools."""

from fm_mcp.tools.approval.approve_request import approve_request
from fm_mcp.tools.approval.get_approval_history import get_approval_history
from fm_mcp.tools.approval.get_pending_approvals import get_pending_approvals
from fm_mcp.tools.approval.reject_request import reject_request

TOOLS = (
    get_pending_approvals,
    approve_request,
    reject_request,
    get_approval_history,
)
