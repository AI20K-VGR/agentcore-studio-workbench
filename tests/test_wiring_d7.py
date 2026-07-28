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
from studio_contracts import EmbeddingService, TraceEvent
from studio_engine.interpreter import run

from studio_workbench import create_recipe_d6

ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")


class MockGatewayEmbedding:
    """Offline Fake/Mock GatewayEmbedding implementation adhering to studio_contracts.EmbeddingService protocol.
    
    Contract invariant: must implement `async def embed(self, texts: list[str]) -> list[list[float]]`.
    Ensures CI runs 100% offline without hitting real external network endpoints.
    """

    def __init__(self, dimension: int = 1536) -> None:
        self.dimension = dimension
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[0.1] * self.dimension for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        res = await self.embed([text])
        return res[0]

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return await self.embed(list(texts))


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
    """DoD 1 & DoD 2: Constructor Dependency Injection (DIP) & Protocol Compatibility.
    
    Verifies that `interpreter.run()` accepts any valid `EmbeddingService` implementation
    (such as `MockGatewayEmbedding`) via constructor-DI without requiring any changes to `interpreter.py`.
    
    Note: In the current engine DAG walk (v0), `LlmStepExecutor` receives `embedding` via DI but does
    not invoke `.embed()` during execution (`executors.py:160`). This test validates DIP structural
    wiring and signature compatibility at the workbench integration boundary.
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

    # 1. Verify interpreter.run() accepts MockGatewayEmbedding via DI seamlessly
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

    # Verify execution completes without errors and trace_writer captured all 4 node events
    assert len(trace_writer.events) == 4
    assert isinstance(result.final_state["n1"], list)

    # 2. Independent assertion: verify MockGatewayEmbedding structural compliance with EmbeddingService protocol
    assert isinstance(mock_gateway_embedding, EmbeddingService)


@pytest.mark.asyncio
async def test_mock_gateway_embedding_standalone_protocol_behavior() -> None:
    """Standalone unit test for MockGatewayEmbedding behavior.
    
    Verifies that MockGatewayEmbedding's `embed()` method returns deterministic vectors matching
    the configured dimension and correctly records invocation calls independently of interpreter.run().
    """
    mock_emb = MockGatewayEmbedding(dimension=768)
    vectors = await mock_emb.embed(["query text 1", "query text 2"])
    
    assert len(vectors) == 2
    assert len(vectors[0]) == 768
    assert len(vectors[1]) == 768
    assert mock_emb.calls == [["query text 1", "query text 2"]]


