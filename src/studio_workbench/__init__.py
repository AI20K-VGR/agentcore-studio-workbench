"""AgentCore Studio Workbench — form+canvas UI wiring, recipe validator/agent-shape-lint, Tenant-Wall.

Owner: SWE. Phase 7 fills in `wb.*` DDL (`schema.ddl()`) + the validator/publish/Tenant-Wall
seams (all 3 ship as spec stubs — `NotImplementedError`, real bodies left for the SWE OJT
candidate). `agent_shape_lint`/`agent_topology_lint`/`enforce_agent_shape`/
`enforce_agent_topology`/`publish`/`rollback` are re-exported here for ergonomic top-level
import (mirrors `studio_contracts`'s own `__init__.py` pattern); `resolve_tenant_id` (Tenant-Wall)
stays reachable only via its own `studio_workbench.tenant_wall` submodule.

app#44: `graph_lint` (DAG-topology, 7 rules) is REMOVED — see `validator.py` module docstring.
Anything outside this package still importing `graph_lint` (`apps/studio`, `apps/web`'s TS
mirror `graphLint.ts`) breaks until updated separately; out of scope for this change.
"""

from studio_workbench.canvas import recipe_from_canvas
from studio_workbench.publish import publish, recipe_hash, rollback
from studio_workbench.recipe import (
    ANKOR_ID,
    BOREA_ID,
    build_agent_config,
    create_recipe,
)
from studio_workbench.recipe_ops import with_query, without_query
from studio_workbench.validator import (
    agent_shape_lint,
    agent_topology_lint,
    enforce_agent_shape,
    enforce_agent_topology,
)

__all__ = [
    "ANKOR_ID",
    "BOREA_ID",
    "agent_shape_lint",
    "agent_topology_lint",
    "build_agent_config",
    "create_recipe",
    "enforce_agent_shape",
    "enforce_agent_topology",
    "publish",
    "recipe_from_canvas",
    "recipe_hash",
    "rollback",
    "with_query",
    "without_query",
]
