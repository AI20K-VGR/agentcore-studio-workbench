"""graph-lint spec tests (R-SPEC A1#1 :36) — `validator.graph_lint` ships as a spec stub this
phase: it unconditionally raises `NotImplementedError` (spec SWE, real 4-rule body left for the
OJT candidate). Both tests below are `xfail(strict=False)` (builtin marker — no pyproject change
needed, `xfail_strict` is not set there so the default is already False; the explicit `strict=False`
here just makes that non-negotiable regardless of any future global config):

- `test_graph_lint_not_implemented` pins the CURRENT stub behavior (raises `NotImplementedError`)
  — this assertion actually PASSES against today's stub; wrapping it in `xfail(strict=False)`
    means that PASS reports as XPASS (harmless, never fails the suite) rather than a plain green
    test that would silently stop meaning anything the day the real body lands and starts
    raising something else instead.
- `test_lint_rejects_bad_graph` pins the FUTURE real behavior (rule-specific rejection) — this
  genuinely fails today (`NotImplementedError`, not the rule-specific `ValueError`) and is meant
  to flip green (or get promoted off `xfail`) the day `graph_lint()` is implemented for real.

`strict=False` matters here specifically because an OJT candidate implementing rule 1 first
would otherwise turn `test_lint_rejects_bad_graph` into an XPASS-that-fails-the-suite the moment
they get partway done — punishing incremental progress is the wrong incentive for this phase.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from studio_contracts import AgentConfig, Dag, Edge, KbBinding, Node, NodeType, Recipe, ScorecardThreshold
from studio_workbench.validator import graph_lint

ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")


def _valid_recipe() -> Recipe:
    return Recipe(
        agent_id="agent-1",
        tenant_id=ANKOR_ID,
        agent_config=AgentConfig(
            instructions="Answer from KB only.",
            model="gpt-4o-mini",
            tool_whitelist=["kb_search"],
        ),
        dag=Dag(
            nodes=[
                Node(id="n1", type=NodeType.KB_RETRIEVE, params={}),
                Node(id="n2", type=NodeType.END, params={}),
            ],
            edges=[Edge(from_="n1", to="n2", when=None)],
        ),
        kb_binding=KbBinding(kb_id="kb-1", scope="ankor/public"),
        golden_set_ref="golden-set-1",
        scorecard_threshold=ScorecardThreshold(success=0.9, citation_accuracy=0.95),
    )


@pytest.mark.xfail(reason="spec SWE fills graph-lint", strict=False)
def test_graph_lint_not_implemented() -> None:
    """KHÓA: `graph_lint`'s current spec body is `NotImplementedError` (P7 stub — SWE OJT fills
    in the real 4-rule DAG validator later; the engine (P6) must never interpret a recipe that
    has not passed this gate, per R-SPEC A1#1: "recipe không qua validator = không interpret")."""
    with pytest.raises(NotImplementedError):
        graph_lint(_valid_recipe())


@pytest.mark.xfail(reason="spec SWE fills graph-lint", strict=False)
def test_lint_rejects_bad_graph() -> None:
    """KHÓA: the 4 graph-lint rules (R-SPEC A1#1 :36) — node ∈ 6 closed NodeType, no forbidden
    cycle, every edge has a resolvable destination, every `tool-call` tool ∈
    `agent_config.tool_whitelist`. Case 1 uses `model_construct` (bypasses pydantic validation) to
    simulate a node type that reached `graph_lint` WITHOUT having passed through the closed
    contract — e.g. a stale/foreign value read back from `wb.recipes.recipe` (jsonb) after a
    future contract change; the other 3 cases are plain, validly-typed Recipes that still violate
    a structural DAG rule pydantic itself does not check. All 4 currently raise
    `NotImplementedError` (the stub) instead of the rule-specific rejection this test expects."""
    base = _valid_recipe()

    # 1. node ∉ 6 closed NodeType.
    bad_node_type = base.model_copy(
        update={
            "dag": Dag.model_construct(
                nodes=[Node.model_construct(id="n1", type="not-a-real-type", params={})],  # type: ignore[arg-type]  # intentional: simulate a stale/foreign node type the closed enum would reject
                edges=[],
            )
        }
    )
    with pytest.raises(ValueError, match="NodeType"):
        graph_lint(bad_node_type)

    # 2. forbidden cycle: n1 -> n2 -> n1.
    cyclic = base.model_copy(
        update={
            "dag": Dag(
                nodes=[
                    Node(id="n1", type=NodeType.KB_RETRIEVE, params={}),
                    Node(id="n2", type=NodeType.LLM_STEP, params={}),
                ],
                edges=[
                    Edge(from_="n1", to="n2", when=None),
                    Edge(from_="n2", to="n1", when=None),
                ],
            )
        }
    )
    with pytest.raises(ValueError, match="cycle"):
        graph_lint(cyclic)

    # 3. edge with no resolvable destination.
    dangling_edge = base.model_copy(
        update={
            "dag": Dag(
                nodes=[Node(id="n1", type=NodeType.KB_RETRIEVE, params={})],
                edges=[Edge(from_="n1", to="ghost", when=None)],
            )
        }
    )
    with pytest.raises(ValueError, match="destination"):
        graph_lint(dangling_edge)

    # 4. tool ∉ tool_whitelist.
    tool_violation = base.model_copy(
        update={
            "agent_config": AgentConfig(
                instructions="x",
                model="gpt-4o-mini",
                tool_whitelist=["allowed_tool"],
            ),
            "dag": Dag(
                nodes=[
                    Node(id="n1", type=NodeType.TOOL_CALL, params={"tool": "forbidden_tool"}),
                    Node(id="n2", type=NodeType.END, params={}),
                ],
                edges=[Edge(from_="n1", to="n2", when=None)],
            ),
        }
    )
    with pytest.raises(ValueError, match="whitelist"):
        graph_lint(tool_violation)
