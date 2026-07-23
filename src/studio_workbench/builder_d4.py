"""Recipe Builder Day 4 for Workbench (SWE owner — Thiệu Quang Minh).

Converts user form inputs from Workbench UI into a validated `Recipe` (R-SPEC A1#1)
containing `kb_binding.{kb_id, scope}` for multi-tenant KB scope declaration (Issue #18).
"""

from __future__ import annotations

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


def create_recipe_d4(
    agent_id: str = "agent-callisto-d4",
    tenant: str = "ankor",
    instructions: str = "Tra cứu quy trình và bảo mật Callisto.",
    model: str = "gemini-2.5-flash",
    kb_id: str = "kb-callisto-v1",
    scope: str = "ankor/public",
    tool_whitelist: list[str] | None = None,
) -> Recipe:
    """Build a Day 4 Recipe instance containing `kb_binding.{kb_id, scope}`.

    Wiring `recipe -> interpreter` relies on `recipe.kb_binding` to pass
    the declared KB scope to `kb.search`.
    """
    if tool_whitelist is None:
        tool_whitelist = ["kb_search"]

    config = build_agent_config(
        instructions=instructions,
        model=model,
        tool_whitelist=tool_whitelist,
    )

    kb_bind = KbBinding(
        kb_id=kb_id,
        scope=scope,
    )

    # Extract tenant and section_roles from scope ("ankor/public")
    if "/" in scope:
        tenant_from_scope, roles_part = scope.split("/", 1)
        section_roles = [r.strip() for r in roles_part.split(",") if r.strip()]
    else:
        tenant_from_scope = tenant
        section_roles = [scope] if scope else ["public"]

    nodes = [
        Node(
            id="n1",
            type=NodeType.KB_RETRIEVE,
            params={
                "query": "Callisto security policy",
                "tenant": tenant_from_scope,
                "section_roles": section_roles,
                "top_k": 3,
            },
        ),
        Node(id="n2", type=NodeType.LLM_STEP, params={"temperature": 0.0}),
        Node(id="n3", type=NodeType.TOOL_CALL, params={"tool": "kb_search"}),
        Node(id="n4", type=NodeType.END, params={}),
    ]

    edges = [
        Edge(from_="n1", to="n2"),
        Edge(from_="n2", to="n3"),
        Edge(from_="n3", to="n4"),
    ]

    return Recipe(
        agent_id=agent_id,
        tenant=tenant,
        agent_config=config,
        dag=Dag(nodes=nodes, edges=edges),
        kb_binding=kb_bind,
        golden_set_ref="golden-set-d4-callisto",
        scorecard_threshold=ScorecardThreshold(success=0.9, citation_accuracy=0.95),
    )
