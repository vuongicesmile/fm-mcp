"""FM-owned data profiling MCP tools."""

from fm_mcp.tools.profiling.get_data_profiling_overview import get_data_profiling_overview
from fm_mcp.tools.profiling.get_data_profiling_run import get_data_profiling_run
from fm_mcp.tools.profiling.get_masked_raw_sample import get_masked_raw_sample
from fm_mcp.tools.profiling.list_data_profiling_assets import list_data_profiling_assets
from fm_mcp.tools.profiling.run_data_profiling import run_data_profiling
from fm_mcp.tools.profiling.seed_data_profiling_demo import seed_data_profiling_demo

TOOLS = (
    list_data_profiling_assets,
    run_data_profiling,
    get_data_profiling_run,
    get_data_profiling_overview,
    get_masked_raw_sample,
    seed_data_profiling_demo,
)
