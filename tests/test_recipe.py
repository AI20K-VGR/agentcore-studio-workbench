"""Test suite for studio_workbench.recipe module and create_recipe function.

Tests dynamic recipe creation with 2-node, 3-node, and N-node DAGs, as well as
compatibility with interpreter.run().
"""

from __future__ import annotations

import pytest
from studio_contracts import Edge, Node, NodeType, TraceEvent
from studio_engine.interpreter import run

from studio_workbench import (
    ANKOR_ID,
    build_agent_config,
    create_recipe,
    create_recipe_d4,
)
from studio_workbench.tenant_wall import ResolvedContext


def test_build_agent_config() -> None:
    """Test build_agent_config helper function."""
    config = build_agent_config(
        instructions="System instructions",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search"],
        temperature=0.5,
    )
    assert config.instructions == "System instructions"
    assert config.model == "gemini-2.5-flash"
    assert config.tool_whitelist == ["kb_search"]
    assert config.temperature == 0.5


def test_create_recipe_2_nodes() -> None:
    """Test building a recipe with 2 nodes (LLM_STEP -> END)."""
    nodes = [
        Node(id="n1", type=NodeType.LLM_STEP, params={"temperature": 0.5}),
        Node(id="n2", type=NodeType.END, params={}),
    ]
    edges = [
        Edge(from_="n1", to="n2"),
    ]

    recipe = create_recipe(
        agent_id="agent-2-nodes",
        tenant_id=ANKOR_ID,
        instructions="Direct LLM chat without KB",
        tool_whitelist=[],
        nodes=nodes,
        edges=edges,
        temperature=0.3,
    )

    assert recipe.agent_id == "agent-2-nodes"
    assert recipe.tenant_id == ANKOR_ID
    assert recipe.agent_config.model == "gemini-2.5-flash"
    assert recipe.agent_config.temperature == 0.3
    assert len(recipe.dag.nodes) == 2
    assert len(recipe.dag.edges) == 1
    assert recipe.dag.nodes[0].type == NodeType.LLM_STEP
    assert recipe.dag.nodes[1].type == NodeType.END
    assert recipe.kb_binding is not None
    assert recipe.kb_binding.kb_id == "kb-callisto-v1"
    assert recipe.kb_binding.scope == "ankor/public"
    assert recipe.scorecard_threshold.success == 0.9
    assert recipe.scorecard_threshold.citation_accuracy == 0.95


def test_create_recipe_3_nodes_with_kb() -> None:
    """Test building a recipe with 3 nodes (KB_RETRIEVE -> LLM_STEP -> END) and hardcoded KB binding."""
    nodes = [
        Node(id="n1", type=NodeType.KB_RETRIEVE, params={"query": "Callisto policy"}),
        Node(id="n2", type=NodeType.LLM_STEP, params={"temperature": 0.0}),
        Node(id="n3", type=NodeType.END, params={}),
    ]
    edges = [
        Edge(from_="n1", to="n2"),
        Edge(from_="n2", to="n3"),
    ]

    recipe = create_recipe(
        agent_id="agent-3-nodes-kb",
        tenant_id=ANKOR_ID,
        instructions="Search KB then answer",
        tool_whitelist=["kb_search"],
        nodes=nodes,
        edges=edges,
    )

    assert recipe.agent_id == "agent-3-nodes-kb"
    assert len(recipe.dag.nodes) == 3
    assert len(recipe.dag.edges) == 2
    assert recipe.agent_config.temperature == 0.7
    assert recipe.kb_binding is not None
    assert recipe.kb_binding.kb_id == "kb-callisto-v1"
    assert recipe.kb_binding.scope == "ankor/public"


def test_legacy_builders_compatibility() -> None:
    """Test that create_recipe_d4 works properly from unified builder.

    `create_recipe_d3`/`create_sample_recipe_d3` removed (day21 cleanup) — 0 caller ngoài
    `packages/workbench` (đã kiểm kê toàn repo), hành vi là tập con thật sự của `create_recipe_d4`.
    `create_recipe_d6` removed cùng lý do (workbench#31 follow-up) — 0 caller production, chỉ tự
    tham chiếu trong test của chính package; `create_recipe` là builder Form-Feed còn lại.
    """
    r4 = create_recipe_d4(agent_id="d4-agent")
    assert r4.agent_id == "d4-agent"
    assert len(r4.dag.nodes) == 3


def test_default_golden_set_ref_points_to_golden_30() -> None:
    """D16 (kit#107): default `golden_set_ref` must pin to the real 30-case golden set, not the
    stale 5-case smoke set. `create_recipe_d4` is the production call path
    (`apps/studio/src/studio_app/eval_adapter.py:98`, called WITHOUT an explicit `golden_set_ref`)
    — without this pin, a future edit/revert of the literal has zero local test signal (review
    finding, TranBaDat2607, workbench#20)."""
    nodes = [
        Node(id="n1", type=NodeType.LLM_STEP, params={}),
        Node(id="n2", type=NodeType.END, params={}),
    ]
    edges = [Edge(from_="n1", to="n2")]

    r_dynamic = create_recipe(
        agent_id="agent-golden-ref-check",
        tenant_id=ANKOR_ID,
        instructions="inst",
        tool_whitelist=[],
        nodes=nodes,
        edges=edges,
    )
    assert r_dynamic.golden_set_ref == "callisto-golden-30-v1"

    r4 = create_recipe_d4()
    assert r4.golden_set_ref == "callisto-golden-30-v1"


class _NoOpTraceWriter:
    """Conforming no-op TraceWriter seam for wiring tests."""

    async def write(self, event: TraceEvent) -> None:
        del event


@pytest.mark.asyncio
async def test_recipe_wiring_to_interpreter() -> None:
    """Test wiring: passing a 2-node recipe into engine's interpreter.run()."""
    from studio_engine.demo_stubs import EmptyEmbedding, EmptyKbSearch, FixtureLLM

    nodes = [
        Node(id="n1", type=NodeType.LLM_STEP, params={"temperature": 0.0}),
        Node(id="n2", type=NodeType.END, params={}),
    ]
    edges = [
        Edge(from_="n1", to="n2"),
    ]

    recipe = create_recipe(
        agent_id="agent-2-nodes-wiring",
        tenant_id=ANKOR_ID,
        instructions="Direct answer",
        tool_whitelist=[],
        nodes=nodes,
        edges=edges,
    )

    result = await run(
        recipe,
        kb_search=EmptyKbSearch(),
        llm=FixtureLLM("smoke-01"),
        embedding=EmptyEmbedding(),
        trace_writer=_NoOpTraceWriter(),
        session_context=ResolvedContext(tenant_id=ANKOR_ID, user="test-harness", roles=["public"]),
    )

    assert result.run_id is not None
    assert "n1" in result.final_state
    assert "n2" in result.final_state

