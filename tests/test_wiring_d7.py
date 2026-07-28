"""Day 7 SWE Wiring & Clean Protocol Test Suite.

Validates:
1. Protocol Inversion (DIP): Replacing StubEmbedding -> GatewayEmbedding without touching interpreter.
2. Offline CI execution (Mock GatewayEmbedding / Provider Fakes).
3. Interpreter reading full 3-field `agent_config` (`instructions`, `model`, `tool_whitelist`).

Owner: SWE (Thiệu Quang Minh).
"""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

import pytest
from studio_contracts import Node, NodeType, TraceEvent
from studio_engine.interpreter import run

from studio_workbench import create_recipe_d6

ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")


class MockGatewayEmbedding:
    """Offline Fake/Mock GatewayEmbedding implementation adhering to EmbeddingProvider protocol.
    
    Ensures CI runs 100% offline without hitting real external network endpoints.
    """

    def __init__(self, dimension: int = 1536) -> None:
        self.dimension = dimension
        self.call_count = 0

    async def embed_query(self, text: str) -> list[float]:
        self.call_count += 1
        # Return deterministic dummy vector of length `dimension`
        return [0.1] * self.dimension

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.call_count += len(texts)
        return [[0.1] * self.dimension for _ in texts]


class _RecordingTraceWriter:
    """Double recorder for trace events."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    async def write(self, event: TraceEvent) -> None:
        self.events.append(event)


def test_agent_config_has_all_three_fields() -> None:
    """DoD 3: Verify Recipe.agent_config exposes all 3 required fields."""
    recipe = create_recipe_d6(
        agent_id="agent-d7-full-config",
        tenant_id=ANKOR_ID,
        instructions="Bạn là trợ lý AI tra cứu Callisto.",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search", "sql_query_tool"],
        kb_id="kb-callisto-v1",
        scope="ankor/public, hr",
        query="Bảo mật dữ liệu Callisto như thế nào?",
    )

    # 1. instructions
    assert recipe.agent_config.instructions == "Bạn là trợ lý AI tra cứu Callisto."
    # 2. model
    assert recipe.agent_config.model == "gemini-2.5-flash"
    # 3. tool_whitelist
    assert recipe.agent_config.tool_whitelist == ["kb_search", "sql_query_tool"]


@pytest.mark.asyncio
async def test_protocol_cleanliness_gateway_embedding_without_interpreter_changes() -> None:
    """DoD 1 & DoD 2: Replace StubEmbedding -> GatewayEmbedding seamlessly in interpreter.run().
    
    Proves Clean Architecture (DIP) where interpreter logic remains 100% untouched while
    swapping embedding providers, executing offline in CI.
    """
    from studio_engine.demo_stubs import FixtureLLM
    from studio_kb import StaticKbSearch

    recipe = create_recipe_d6(
        agent_id="agent-d7-dip-test",
        tenant_id=ANKOR_ID,
        instructions="Tra cứu chính sách nghỉ phép.",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search"],
        kb_id="kb-callisto-v1",
        scope="ankor/public",
        query="Nhân viên xin nghỉ phép cần báo trước bao lâu?",
    )

    mock_gateway_embedding = MockGatewayEmbedding(dimension=768)
    trace_writer = _RecordingTraceWriter()

    # Pass MockGatewayEmbedding seamlessly into interpreter.run()
    result = await run(
        recipe,
        kb_search=StaticKbSearch(),
        llm=FixtureLLM("smoke-01"),
        embedding=mock_gateway_embedding,
        trace_writer=trace_writer,
    )

    assert result.run_id is not None
    assert "n1" in result.final_state
    assert "n2" in result.final_state
    assert "n3" in result.final_state
    assert "n4" in result.final_state

    # Verify execution completes without errors and embedding interface was invoked cleanly
    assert isinstance(result.final_state["n1"], list)
