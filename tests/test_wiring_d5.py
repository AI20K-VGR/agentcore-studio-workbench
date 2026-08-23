"""Test suite for Day 5 SWE wiring — Workbench Recipe -> Interpreter trace emission.

Owner: SWE (Thiệu Quang Minh — Issue #23 / DoD Day 5).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from studio_contracts import TraceEvent
from studio_engine.demo_stubs import EmptyEmbedding, EmptyKbSearch, FixtureLLM
from studio_engine.interpreter import run

from studio_workbench import create_recipe_d4
from studio_workbench.tenant_wall import ResolvedContext

_ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")


class _RecordingTraceWriter:
    """TraceWriter sink for verifying trace event emission in Workbench integration tests."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    async def write(self, event: TraceEvent) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_workbench_recipe_emits_trace_events_via_interpreter() -> None:
    """Verify that a Recipe built by Workbench (Day 4/5) emits 4 TraceEvents when executed by Interpreter."""
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
    assert len(writer.events) == 4

    # Verify that every trace event has matching run_id, agent_id, tenant_id
    for event in writer.events:
        assert event.run_id == result.run_id
        assert event.agent_id == recipe.agent_id
        assert event.tenant_id == recipe.tenant_id
        assert event.ts is not None

    # Verify node execution sequence in trace events: n1 -> n2 -> n3 -> n4
    node_ids = [e.node_id for e in writer.events]
    assert node_ids == ["n1", "n2", "n3", "n4"]
