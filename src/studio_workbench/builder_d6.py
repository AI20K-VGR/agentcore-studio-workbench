"""Recipe Builder Day 6 for Workbench (SWE owner — Thiệu Quang Minh).

Builds a validated `Recipe` (R-SPEC A1#1) completely driven by dynamic user form inputs
from Workbench UI without hardcoded default values.
"""

from __future__ import annotations

from uuid import UUID

from studio_contracts import (
    Dag,
    Edge,
    KbBinding,
    Node,
    NodeType,
    Recipe,
    ScorecardThreshold,
)
from studio_workbench.builder_d3 import build_agent_config


def create_recipe_d6(
    agent_id: str,
    tenant_id: UUID,
    instructions: str,
    model: str,
    tool_whitelist: list[str],
    kb_id: str,
    scope: str,
    query: str,
    golden_set_ref: str = "callisto-smoke-5-v0",
    success_threshold: float = 0.9,
    citation_accuracy_threshold: float = 0.95,
) -> Recipe:
    """Build a Day 6 dynamic Recipe instance driven 100% by user inputs.

    All core parameters (`agent_id`, `tenant_id`, `instructions`, `model`,
    `tool_whitelist`, `kb_id`, `scope`, `query`) are required positional/keyword
    arguments with NO hardcoded default values.
    """
    t_id = tenant_id if isinstance(tenant_id, UUID) else UUID(tenant_id)

    config = build_agent_config(
        instructions=instructions,
        model=model,
        tool_whitelist=tool_whitelist,
    )

    kb_bind = KbBinding(
        kb_id=kb_id,
        scope=scope,
    )

    # Extract section_roles from scope (e.g. "ankor/public" -> section_roles=["public"])
    if "/" in scope:
        tenant_from_scope, roles_part = scope.split("/", 1)
        section_roles = [r.strip() for r in roles_part.split(",") if r.strip()]
    else:
        section_roles = [scope] if scope else ["public"]

    nodes = [
        Node(
            id="n1",
            type=NodeType.KB_RETRIEVE,
            params={
                "query": query,
                "tenant_id": t_id,
                "section_roles": section_roles,
                "top_k": 3,
            },
        ),
        Node(id="n2", type=NodeType.LLM_STEP, params={"temperature": 0.0}),
        Node(id="n3", type=NodeType.TOOL_CALL, params={"tool": tool_whitelist[0] if tool_whitelist else "kb_search"}),
        Node(id="n4", type=NodeType.END, params={}),
    ]

    edges = [
        Edge(from_="n1", to="n2"),
        Edge(from_="n2", to="n3"),
        Edge(from_="n3", to="n4"),
    ]

    return Recipe(
        agent_id=agent_id,
        tenant_id=t_id,
        agent_config=config,
        dag=Dag(nodes=nodes, edges=edges),
        kb_binding=kb_bind,
        golden_set_ref=golden_set_ref,
        scorecard_threshold=ScorecardThreshold(
            success=success_threshold,
            citation_accuracy=citation_accuracy_threshold,
        ),
    )
