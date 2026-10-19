"""Risk MCP tools."""

from fm_mcp.tools.risk.assess_risk import assess_risk
from fm_mcp.tools.risk.create_risk import create_risk
from fm_mcp.tools.risk.get_risk_heatmap import get_risk_heatmap
from fm_mcp.tools.risk.get_risk_register import get_risk_register
from fm_mcp.tools.risk.update_risk import update_risk

TOOLS = (
    create_risk,
    update_risk,
    get_risk_register,
    assess_risk,
    get_risk_heatmap,
)
