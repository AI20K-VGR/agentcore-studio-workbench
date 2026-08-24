"""graph-lint spec tests (R-SPEC A1#1 :36) — `validator.graph_lint` real 4-rule body (D11).

- `test_graph_lint_accepts_valid_recipe` replaces the old `test_graph_lint_not_implemented`
  (which pinned the stub's unconditional `NotImplementedError`): now that the real body is
  implemented, a structurally valid recipe must pass cleanly (return `None`), not raise.
- `test_lint_rejects_bad_graph` pins the 4 rule-specific rejections and is promoted off
  `xfail` — it now passes for real against the implemented body.
"""

from __future__ import annotations

from uuid import UUID

import pytest
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

from studio_workbench.validator import graph_lint

ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")


def _valid_recipe() -> Recipe:
    return Recipe(
        agent_id="agent-1",
        tenant_id=ANKOR_ID,
        agent_config=AgentConfig(
            system_prompt="Answer from KB only.",
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


def test_graph_lint_accepts_valid_recipe() -> None:
    """KHÓA: a structurally valid recipe (6-closed node types, no cycle, every edge resolves,
    every tool-call tool ∈ whitelist) passes `graph_lint` cleanly — returns `None`, raises
    nothing. The engine (AIE-1) must never interpret a recipe that has not passed this gate,
    per R-SPEC A1#1: "recipe không qua validator = không interpret"."""
    graph_lint(_valid_recipe())  # must not raise


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
                nodes=[
                    Node.model_construct(id="n1", type="not-a-real-type", params={})  # type: ignore[arg-type]  # intentional: simulate a stale/foreign node type the closed enum would reject
                ],
                edges=[],
            )
        }
    )
    with pytest.raises(ValueError, match="NodeType"):
        graph_lint(bad_node_type)

    # 2. forbidden cycle: n0 -> n1 -> n2 -> n1. n0 gives the DAG a single, unambiguous start
    # node (rule 3) with every node still ≤ 1 outgoing edge (rule 4), isolating this case to
    # rule 5's cycle check alone (n1 <-> n2).
    cyclic = base.model_copy(
        update={
            "dag": Dag(
                nodes=[
                    Node(id="n0", type=NodeType.KB_RETRIEVE, params={}),
                    Node(id="n1", type=NodeType.LLM_STEP, params={}),
                    Node(id="n2", type=NodeType.LLM_STEP, params={}),
                ],
                edges=[
                    Edge(from_="n0", to="n1", when=None),
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
                system_prompt="x",
                model="gpt-4o-mini",
                tool_whitelist=["allowed_tool"],
            ),
            "dag": Dag(
                nodes=[
                    Node(
                        id="n1",
                        type=NodeType.TOOL_CALL,
                        params={"tool": "forbidden_tool"},
                    ),
                    Node(id="n2", type=NodeType.END, params={}),
                ],
                edges=[Edge(from_="n1", to="n2", when=None)],
            ),
        }
    )
    with pytest.raises(ValueError, match="whitelist"):
        graph_lint(tool_violation)


def test_lint_rejects_zero_start_nodes() -> None:
    """KHÓA (rule 3, kit#87 — request from AIE-1): a DAG where every node has an incoming
    edge (2-node mutual cycle) has 0 start-node candidates. `_valid_recipe`'s single-edge
    n1->n2 has n1 as start; adding n2->n1 removes it without introducing a >1-outgoing-edge
    node, isolating this case to rule 3 alone (rule 5's cycle check would also fire on this
    input, but rule 3 runs first)."""
    recipe = _valid_recipe().model_copy(
        update={
            "dag": Dag(
                nodes=[
                    Node(id="n1", type=NodeType.KB_RETRIEVE, params={}),
                    Node(id="n2", type=NodeType.END, params={}),
                ],
                edges=[
                    Edge(from_="n1", to="n2", when=None),
                    Edge(from_="n2", to="n1", when=None),
                ],
            )
        }
    )
    with pytest.raises(ValueError, match="start node"):
        graph_lint(recipe)


def test_lint_rejects_multiple_start_nodes() -> None:
    """KHÓA (rule 3, kit#87): two disconnected chains in one recipe.dag means 2 nodes with no
    incoming edge — the interpreter would have no unambiguous entry point."""
    recipe = _valid_recipe().model_copy(
        update={
            "dag": Dag(
                nodes=[
                    Node(id="n1", type=NodeType.KB_RETRIEVE, params={}),
                    Node(id="n2", type=NodeType.END, params={}),
                    Node(id="n3", type=NodeType.LLM_STEP, params={}),
                    Node(id="n4", type=NodeType.END, params={}),
                ],
                edges=[
                    Edge(from_="n1", to="n2", when=None),
                    Edge(from_="n3", to="n4", when=None),
                ],
            )
        }
    )
    with pytest.raises(ValueError, match="start node"):
        graph_lint(recipe)


def test_lint_rejects_more_than_one_outgoing_edge() -> None:
    """KHÓA (rule 4, kit#87 — TEMPORARY, tied to AIE-1's `ConditionExecutor` progress): a node
    with 2 outgoing edges (real `condition` branching) is rejected because the interpreter
    cannot walk a branch yet. This must be relaxed once `ConditionExecutor` ships (see
    validator.py module docstring) — do not delete this test when that happens, update it to
    assert the new expected behavior instead."""
    recipe = _valid_recipe().model_copy(
        update={
            "dag": Dag(
                nodes=[
                    Node(id="n1", type=NodeType.CONDITION, params={}),
                    Node(id="n2", type=NodeType.END, params={}),
                    Node(id="n3", type=NodeType.END, params={}),
                ],
                edges=[
                    Edge(from_="n1", to="n2", when="true"),
                    Edge(from_="n1", to="n3", when="false"),
                ],
            )
        }
    )
    with pytest.raises(ValueError, match="outgoing edge"):
        graph_lint(recipe)


def test_lint_rejects_walk_not_ending_at_end_node() -> None:
    """KHÓA (rule 6, kit#87 — request from AIE-1): a single-successor chain that runs out of
    edges before reaching an `end` node must be rejected, not merely accepted because it is
    otherwise structurally sound (1 start node, ≤1 outgoing edge each, acyclic)."""
    recipe = _valid_recipe().model_copy(
        update={
            "dag": Dag(
                nodes=[
                    Node(id="n1", type=NodeType.KB_RETRIEVE, params={}),
                    Node(id="n2", type=NodeType.LLM_STEP, params={}),
                ],
                edges=[Edge(from_="n1", to="n2", when=None)],
            )
        }
    )
    with pytest.raises(ValueError, match="end"):
        graph_lint(recipe)


def test_lint_rejects_llm_step_with_multiple_outgoing_edges() -> None:
    """KHÓA: node LLM_STEP with >1 outgoing edges (fan-out) is strictly rejected by rule 4."""
    recipe = _valid_recipe().model_copy(
        update={
            "agent_config": AgentConfig(
                system_prompt="x",
                model="gpt-4o-mini",
                tool_whitelist=["calculator", "current_datetime"],
            ),
            "dag": Dag(
                nodes=[
                    Node(id="n1", type=NodeType.LLM_STEP, params={}),
                    Node(id="t1", type=NodeType.TOOL_CALL, params={"tool": "calculator"}),
                    Node(id="t2", type=NodeType.TOOL_CALL, params={"tool": "current_datetime"}),
                ],
                edges=[
                    Edge(from_="n1", to="t1", when=None),
                    Edge(from_="n1", to="t2", when=None),
                ],
            ),
        }
    )
    with pytest.raises(ValueError, match="outgoing edge"):
        graph_lint(recipe)
