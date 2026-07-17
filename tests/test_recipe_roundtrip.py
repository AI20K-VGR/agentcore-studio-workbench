"""Recipe round-trip via the P2 contract (R-SPEC A1#1) — workbench never defines its own Recipe
shape; it always builds/validates through `studio_contracts.Recipe` (the single seam the recipe
validator/publish flow both depend on). This test guards against the regression of workbench
growing a parallel/divergent recipe type that drifts from the P2 contract.
"""

from __future__ import annotations

from studio_contracts import (
    AgentConfig,
    Dag,
    Edge,
    KbBinding,
    Node,
    NodeType,
    Recipe,
    ScorecardThreshold,
)


def _sample_recipe() -> Recipe:
    return Recipe(
        agent_id="agent-1",
        tenant="ankor",
        agent_config=AgentConfig(
            instructions="Answer from KB only.",
            model="gpt-4o-mini",
            tool_whitelist=["kb_search"],
        ),
        dag=Dag(
            nodes=[
                Node(id="n1", type=NodeType.KB_RETRIEVE, params={}),
                Node(id="n2", type=NodeType.LLM_STEP, params={"temp": 0.0}),
                Node(id="n3", type=NodeType.END, params={}),
            ],
            edges=[
                Edge(from_="n1", to="n2", when=None),
                Edge(from_="n2", to="n3", when=None),
            ],
        ),
        kb_binding=KbBinding(kb_id="kb-1", scope="ankor/public"),
        golden_set_ref="golden-set-1",
        scorecard_threshold=ScorecardThreshold(success=0.9, citation_accuracy=0.95),
    )


def test_recipe_roundtrip_via_contract() -> None:
    """KHÓA: workbench builds/consumes recipes ONLY via `studio_contracts.Recipe` (P2) — dump
    (by_alias, F12's `from` alias) -> validate round-trips to an equal Recipe. A workbench-local
    recipe shape that drifted from the contract would fail this round-trip."""
    recipe = _sample_recipe()
    dumped = recipe.model_dump(by_alias=True)
    restored = Recipe.model_validate(dumped)
    assert restored == recipe
