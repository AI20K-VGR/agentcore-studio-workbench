"""Test suite for studio_workbench.builder module and create_dynamic_recipe function.

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
    create_dynamic_recipe,
    create_recipe_d3,
    create_recipe_d4,
    create_recipe_d6,
)
from studio_workbench.tenant_wall import ResolvedContext


def test_build_agent_config() -> None:
    """Test build_agent_config helper function."""
    config = build_agent_config(
        instructions="System instructions",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search"],
    )
    assert config.instructions == "System instructions"
    assert config.model == "gemini-2.5-flash"
    assert config.tool_whitelist == ["kb_search"]


def test_create_dynamic_recipe_2_nodes() -> None:
    """Test building a dynamic recipe with 2 nodes (LLM_STEP -> END)."""
    nodes = [
        Node(id="n1", type=NodeType.LLM_STEP, params={"temperature": 0.5}),
        Node(id="n2", type=NodeType.END, params={}),
    ]
    edges = [
        Edge(from_="n1", to="n2"),
    ]

    recipe = create_dynamic_recipe(
        agent_id="agent-2-nodes",
        tenant_id=ANKOR_ID,
        instructions="Direct LLM chat without KB",
        model="gemini-2.5-flash",
        tool_whitelist=[],
        kb_id="kb-callisto-v1",
        scope="ankor/public",
        nodes=nodes,
        edges=edges,
    )

    assert recipe.agent_id == "agent-2-nodes"
    assert recipe.tenant_id == ANKOR_ID
    assert len(recipe.dag.nodes) == 2
    assert len(recipe.dag.edges) == 1
    assert recipe.dag.nodes[0].type == NodeType.LLM_STEP
    assert recipe.dag.nodes[1].type == NodeType.END
    assert recipe.kb_binding is not None
    assert recipe.kb_binding.kb_id == "kb-callisto-v1"
    assert recipe.kb_binding.scope == "ankor/public"


def test_create_dynamic_recipe_missing_kb_or_scope_raises() -> None:
    """Test that missing or empty kb_id or scope raises ValueError."""
    nodes = [
        Node(id="n1", type=NodeType.LLM_STEP, params={}),
        Node(id="n2", type=NodeType.END, params={}),
    ]
    edges = [Edge(from_="n1", to="n2")]

    with pytest.raises(ValueError, match="Cần truyền đầy đủ 'kb_id' và 'scope'"):
        create_dynamic_recipe(
            agent_id="agent-err",
            tenant_id=ANKOR_ID,
            instructions="inst",
            model="gemini-2.5-flash",
            tool_whitelist=[],
            nodes=nodes,
            edges=edges,
            kb_id=None,
            scope=None,
        )

    with pytest.raises(ValueError, match="Cần truyền đầy đủ 'kb_id' và 'scope'"):
        create_dynamic_recipe(
            agent_id="agent-err",
            tenant_id=ANKOR_ID,
            instructions="inst",
            model="gemini-2.5-flash",
            tool_whitelist=[],
            nodes=nodes,
            edges=edges,
            kb_id="",
            scope="",
        )


def test_create_dynamic_recipe_3_nodes_with_kb() -> None:
    """Test building a dynamic recipe with 3 nodes (KB_RETRIEVE -> LLM_STEP -> END) and KB binding."""
    nodes = [
        Node(id="n1", type=NodeType.KB_RETRIEVE, params={"query": "Callisto policy"}),
        Node(id="n2", type=NodeType.LLM_STEP, params={"temperature": 0.0}),
        Node(id="n3", type=NodeType.END, params={}),
    ]
    edges = [
        Edge(from_="n1", to="n2"),
        Edge(from_="n2", to="n3"),
    ]

    recipe = create_dynamic_recipe(
        agent_id="agent-3-nodes-kb",
        tenant_id=ANKOR_ID,
        instructions="Search KB then answer",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search"],
        kb_id="kb-callisto-v1",
        scope="ankor/public",
        nodes=nodes,
        edges=edges,
    )

    assert recipe.agent_id == "agent-3-nodes-kb"
    assert len(recipe.dag.nodes) == 3
    assert len(recipe.dag.edges) == 2
    assert recipe.kb_binding is not None
    assert recipe.kb_binding.kb_id == "kb-callisto-v1"
    assert recipe.kb_binding.scope == "ankor/public"


def test_legacy_builders_compatibility() -> None:
    """Test that create_recipe_d3, d4, d6 work properly from unified builder."""
    r3 = create_recipe_d3()
    assert r3.agent_id == "agent_demo_d3"
    assert len(r3.dag.nodes) == 4

    r4 = create_recipe_d4(agent_id="d4-agent")
    assert r4.agent_id == "d4-agent"
    assert len(r4.dag.nodes) == 4

    r6 = create_recipe_d6(
        agent_id="d6-agent",
        tenant_id=ANKOR_ID,
        instructions="inst",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search"],
        kb_id="kb1",
        scope="public",
        query="query",
    )
    assert r6.agent_id == "d6-agent"
    assert len(r6.dag.nodes) == 4


class _NoOpTraceWriter:
    """Conforming no-op TraceWriter seam for wiring tests."""

    async def write(self, event: TraceEvent) -> None:
        del event


@pytest.mark.asyncio
async def test_dynamic_recipe_wiring_to_interpreter() -> None:
    """Test wiring: passing a 2-node dynamic recipe into engine's interpreter.run()."""
    from studio_engine.demo_stubs import EmptyEmbedding, EmptyKbSearch, FixtureLLM

    nodes = [
        Node(id="n1", type=NodeType.LLM_STEP, params={"temperature": 0.0}),
        Node(id="n2", type=NodeType.END, params={}),
    ]
    edges = [
        Edge(from_="n1", to="n2"),
    ]

    recipe = create_dynamic_recipe(
        agent_id="agent-2-nodes-wiring",
        tenant_id=ANKOR_ID,
        instructions="Direct answer",
        model="gemini-2.5-flash",
        tool_whitelist=[],
        kb_id="kb-callisto-v1",
        scope="ankor/public",
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
