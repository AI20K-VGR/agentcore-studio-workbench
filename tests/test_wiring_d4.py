"""Test suite for Day 4 SWE wiring — kb_binding.{kb_id, scope} & Recipe -> Interpreter entry.

Owner: SWE (Thiệu Quang Minh — Issue #18).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from studio_contracts import Edge, Node, NodeType, TraceEvent
from studio_engine.interpreter import run

from studio_workbench import build_agent_config, create_recipe
from studio_workbench.tenant_wall import ResolvedContext

ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")

_NODES = [
    Node(id="n1", type=NodeType.KB_RETRIEVE, params={"top_k": 3}),
    Node(id="n2", type=NodeType.LLM_STEP, params={"temperature": 0.0}),
    Node(id="n4", type=NodeType.END, params={}),
]
_EDGES = [Edge(from_="n1", to="n2"), Edge(from_="n2", to="n4")]


def test_build_agent_config_from_form_inputs() -> None:
    """Test that build_agent_config creates a valid Pydantic AgentConfig."""
    config = build_agent_config(
        instructions="Hỗ trợ tra cứu quy định Callisto.",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search"],
    )
    assert config.instructions == "Hỗ trợ tra cứu quy định Callisto."
    assert config.model == "gemini-2.5-flash"
    assert config.tool_whitelist == ["kb_search"]


def test_create_recipe_contains_kb_binding() -> None:
    """workbench#41 — `create_recipe_d4` đã bị xoá (nhận `kb_id`/`scope` làm tham số động).
    `create_recipe` hardcode `kb_binding` cố định — khoá giá trị hardcode đó, không còn khoá
    round-trip từ tham số client (không còn tham số nào để round-trip nữa)."""
    recipe = create_recipe(
        agent_id="agent-callisto-01",
        tenant_id=ANKOR_ID,
        instructions="Hỗ trợ tra cứu quy định Callisto.",
        tool_whitelist=[],
        nodes=_NODES,
        edges=_EDGES,
    )

    assert recipe.agent_id == "agent-callisto-01"
    assert recipe.tenant_id == ANKOR_ID
    assert recipe.kb_binding is not None
    assert recipe.kb_binding.kb_id == "kb-callisto-v1"
    assert recipe.kb_binding.scope == "ankor/public"
    # `tenant_id`/`section_roles` KHÔNG còn ở `node.params` (hardening #122) —
    # `interpreter.run()` luôn ghi đè cả 2 từ `session_context` (D8/D17, #111), khai sẵn ở đây chỉ
    # là dữ liệu chết, dễ gây hiểu lầm nó có tác dụng. Khoá sự VẮNG MẶT để chặn regression.
    n1 = recipe.dag.nodes[0]
    assert "tenant_id" not in n1.params
    assert "section_roles" not in n1.params


class _NoOpTraceWriter:
    """Conforming no-op TraceWriter seam for wiring tests."""

    async def write(self, event: TraceEvent) -> None:
        del event


@pytest.mark.asyncio
async def test_wiring_recipe_to_interpreter_entry() -> None:
    """Test wiring: passing Recipe with kb_binding into interpreter.run()."""
    from studio_engine.demo_stubs import EmptyEmbedding, EmptyKbSearch, FixtureLLM

    recipe = create_recipe(
        agent_id="agent-callisto-d4",
        tenant_id=ANKOR_ID,
        instructions="Tra cứu quy trình và bảo mật Callisto.",
        tool_whitelist=[],
        nodes=_NODES,
        edges=_EDGES,
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
