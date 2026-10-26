"""FM-owned data profiling MCP tools."""

from fm_mcp.tools.profiling.get_bms_dashboard import get_bms_dashboard
from fm_mcp.tools.profiling.get_data_profiling_overview import (
    get_data_profiling_overview,
)
from fm_mcp.tools.profiling.get_data_profiling_run import get_data_profiling_run
from fm_mcp.tools.profiling.get_energy_comparison import get_energy_comparison
from fm_mcp.tools.profiling.get_masked_raw_sample import get_masked_raw_sample
from fm_mcp.tools.profiling.list_data_profiling_assets import list_data_profiling_assets
from fm_mcp.tools.profiling.run_data_profiling import run_data_profiling
from fm_mcp.tools.profiling.seed_bad_data_profiling_demo import (
    seed_bad_data_profiling_demo,
)
from fm_mcp.tools.profiling.seed_data_profiling_demo import seed_data_profiling_demo

TOOLS = (
    get_energy_comparison,
    get_bms_dashboard,
    list_data_profiling_assets,
    run_data_profiling,
    get_data_profiling_run,
    get_data_profiling_overview,
    get_masked_raw_sample,
    seed_data_profiling_demo,
    seed_bad_data_profiling_demo,
)
