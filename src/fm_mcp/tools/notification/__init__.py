"""Notification MCP tools."""

from fm_mcp.tools.notification.get_notifications import get_notifications
from fm_mcp.tools.notification.get_overdue_requests import get_overdue_requests
from fm_mcp.tools.notification.send_notification import send_notification

TOOLS = (
    get_notifications,
    send_notification,
    get_overdue_requests,
)
