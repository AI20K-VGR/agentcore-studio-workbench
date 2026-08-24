"""Test suite for Day 5 SWE wiring — Workbench Recipe -> Interpreter trace emission.

Owner: SWE (Thiệu Quang Minh — Issue #23 / DoD Day 5).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from studio_contracts import Edge, Node, NodeType, TraceEvent
from studio_engine.demo_stubs import EmptyEmbedding, EmptyKbSearch, FixtureLLM
from studio_engine.interpreter import run

from studio_workbench import create_recipe, create_recipe_d4
from studio_workbench.tenant_wall import ResolvedContext
from studio_workbench.validator import graph_lint

_ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")


class _RecordingTraceWriter:
    """TraceWriter sink for verifying trace event emission in Workbench integration tests."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    async def write(self, event: TraceEvent) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_workbench_recipe_emits_trace_events_via_interpreter() -> None:
    """Verify that a Recipe built by Workbench (Day 4/5) emits 3 TraceEvents when executed by Interpreter."""
    recipe = create_recipe_d4()
    writer = _RecordingTraceWriter()

    result = await run(
        recipe,
        kb_search=EmptyKbSearch(),
        llm=FixtureLLM("smoke-01"),
        embedding=EmptyEmbedding(),
        trace_writer=writer,
        session_context=ResolvedContext(tenant_id=_ANKOR_ID, user="test-harness", roles=["public"]),
    )

    assert result.run_id is not None
    assert len(writer.events) == 3

    # Verify that every trace event has matching run_id, agent_id, tenant_id
    for event in writer.events:
        assert event.run_id == result.run_id
        assert event.agent_id == recipe.agent_id
        assert event.tenant_id == recipe.tenant_id
        assert event.ts is not None

    # Verify node execution sequence in trace events: n1 -> n2 -> n4
    node_ids = [e.node_id for e in writer.events]
    assert node_ids == ["n1", "n2", "n4"]


@pytest.mark.asyncio
async def test_dynamic_recipe_tool_call_node_runs_via_interpreter() -> None:
    """Real end-to-end coverage for `ToolCallExecutor`/rule 7, kept alive after kit#206 (ADR-D24-01):
    once `create_recipe_d4`/`create_recipe_d6` stopped emitting a `tool-call` node (workbench#31),
    no builder-produced recipe exercised the interpreter's `tool-call` path anymore. `create_recipe`
    is the one builder that still lets a canvas admin declare a real `tool-call` node (a *whitelisted*
    tool, `calculator` — never `kb_search`, see workbench#31), so this locks that path stays wired:
    `graph_lint` accepts a single-path `kb-retrieve -> llm-step -> tool-call -> end` DAG (rule 4 still
    rejects fan-out per kit#206 ADR-D24-01), and the interpreter actually reaches `ToolCallExecutor`.
    """
    nodes = [
        Node(id="n1", type=NodeType.KB_RETRIEVE, params={"query": "q", "top_k": 3}),
        Node(id="n2", type=NodeType.LLM_STEP, params={"temperature": 0.0}),
        Node(id="n3", type=NodeType.TOOL_CALL, params={"tool": "calculator"}),
        Node(id="n4", type=NodeType.END, params={}),
    ]
    edges = [
        Edge(from_="n1", to="n2"),
        Edge(from_="n2", to="n3"),
        Edge(from_="n3", to="n4"),
    ]
    recipe = create_recipe(
        agent_id="agent-tool-call-coverage",
        tenant_id=_ANKOR_ID,
        instructions="x",
        tool_whitelist=["calculator"],
        nodes=nodes,
        edges=edges,
    )
    graph_lint(recipe)  # must pass: single path, no fan-out (kit#206 ADR-D24-01)

    writer = _RecordingTraceWriter()
    result = await run(
        recipe,
        kb_search=EmptyKbSearch(),
        llm=FixtureLLM("smoke-01"),
        embedding=EmptyEmbedding(),
        trace_writer=writer,
        session_context=ResolvedContext(tenant_id=_ANKOR_ID, user="test-harness", roles=["public"]),
    )

    assert result.run_id is not None
    node_ids = [e.node_id for e in writer.events]
    assert node_ids == ["n1", "n2", "n3", "n4"]

    tool_call_event = writer.events[2]
    assert tool_call_event.node_id == "n3"
    assert tool_call_event.outputs.get("tool") == "calculator"
    assert tool_call_event.outputs.get("status") == "stub-dispatched"
