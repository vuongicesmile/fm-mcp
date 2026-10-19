"""Workflow MCP tools."""

from fm_mcp.tools.workflow.close_request import close_request
from fm_mcp.tools.workflow.create_request import create_request
from fm_mcp.tools.workflow.create_workflow import create_workflow
from fm_mcp.tools.workflow.get_request import get_request
from fm_mcp.tools.workflow.get_request_history import get_request_history
from fm_mcp.tools.workflow.list_requests import list_requests
from fm_mcp.tools.workflow.list_workflows import list_workflows
from fm_mcp.tools.workflow.submit_request import submit_request
from fm_mcp.tools.workflow.update_request import update_request

TOOLS = (
    list_workflows,
    create_workflow,
    create_request,
    list_requests,
    get_request,
    update_request,
    submit_request,
    close_request,
    get_request_history,
)
