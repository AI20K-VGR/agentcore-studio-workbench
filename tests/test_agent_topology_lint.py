"""`validator.agent_topology_lint`/`enforce_agent_topology` spec tests (app#44 rewrite).

Replaces the `recipe.dag` half of `test_graph_lint.py` (deleted — `graph_lint()` itself is
removed). Star topology: 1 `llm-step` node at the center, 0-1 `kb-retrieve` + 0..N `tool-call`
nodes as spokes, each directly edged to the LLM node. See `validator.py` module docstring for
the full rationale (`kit#206` — no "tool hub" node, no 7th `NodeType`).
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

from studio_workbench.validator import agent_topology_lint, enforce_agent_topology

# `ANKOR_ID`/`assert_finding_status` khai TẠI CHỖ, không `from conftest import` (workbench#53).
#
# Khớp convention 8 file khác trong package này (`test_publish.py`, `test_wb_schema.py`,
# `test_wiring_d4/d7/d8/d9.py`, ...) — mỗi file tự khai `ANKOR_ID` riêng. Một lượt `/simplify` gom
# hai helper này vào `conftest.py`, và hai file mới của workbench#48 đổi sang `from conftest import`.
#
# Vấn đề: workspace có 6 file `conftest.py` và `tests/` không phải package, nên tên module `conftest`
# bị tranh chấp — bên nào vào `sys.modules` trước thì thắng. Hai triệu chứng đo được:
#
#   mypy packages apps   ->  Module "conftest" has no attribute "ANKOR_ID"   (job `lint` của kit)
#   pytest (gốc kit)     ->  ImportError lúc thu thập, ABORT cả lượt chạy
#
# Cả hai VÔ HÌNH với CI của repo con: job ở đây chỉ chạy `packages/workbench`, nơi không có
# `conftest` nào tranh chấp. Duplicate hai dòng rẻ hơn hẳn mọi cách đi vòng.
ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")


def assert_finding_status(findings: list[dict[str, str]], rule: str, expected: str) -> None:
    actual = next(f["status"] for f in findings if f["rule"] == rule)
    assert actual == expected, f"{rule}: expected status {expected!r}, got {actual!r} ({findings})"


def _recipe(dag: Dag) -> Recipe:
    return Recipe(
        agent_id="agent-1",
        tenant_id=ANKOR_ID,
        agent_config=AgentConfig(system_prompt="hi", model="m", tool_whitelist=["calculator", "current_datetime"]),
        dag=dag,
        kb_binding=KbBinding(kb_id="kb-1", scope="ankor/public"),
        golden_set_ref="golden-set-1",
        scorecard_threshold=ScorecardThreshold(success=0.9, citation_accuracy=0.95),
    )


def _star_dag() -> Dag:
    return Dag(
        nodes=[
            Node(id="llm-1", type=NodeType.LLM_STEP, params={}),
            Node(id="kb-1", type=NodeType.KB_RETRIEVE, params={}),
            Node(id="tool-1", type=NodeType.TOOL_CALL, params={"tool": "calculator"}),
            Node(id="tool-2", type=NodeType.TOOL_CALL, params={"tool": "current_datetime"}),
        ],
        edges=[
            Edge(from_="kb-1", to="llm-1"),
            Edge(from_="tool-1", to="llm-1"),
            Edge(from_="llm-1", to="tool-2"),  # cạnh chiều ngược lại vẫn hợp lệ (không ép chiều)
        ],
    )


def test_valid_star_dag_passes_every_rule() -> None:
    findings = agent_topology_lint(_recipe(_star_dag()))
    assert all(f["status"] == "OK" for f in findings), findings
    enforce_agent_topology(_recipe(_star_dag()))  # must not raise


def test_duplicate_node_id_fails() -> None:
    dag = Dag(
        nodes=[
            Node(id="llm-1", type=NodeType.LLM_STEP, params={}),
            Node(id="llm-1", type=NodeType.TOOL_CALL, params={"tool": "calculator"}),
        ],
        edges=[],
    )
    findings = agent_topology_lint(_recipe(dag))
    assert_finding_status(findings, "dag.no_duplicate_node_ids", "FAIL")


def test_disallowed_node_type_fails() -> None:
    dag = Dag(
        nodes=[
            Node(id="llm-1", type=NodeType.LLM_STEP, params={}),
            Node(id="end-1", type=NodeType.END, params={}),
        ],
        edges=[Edge(from_="llm-1", to="end-1")],
    )
    findings = agent_topology_lint(_recipe(dag))
    assert_finding_status(findings, "dag.only_llm_kb_tool_node_types", "FAIL")


def test_zero_llm_nodes_fails() -> None:
    dag = Dag(nodes=[Node(id="tool-1", type=NodeType.TOOL_CALL, params={"tool": "calculator"})], edges=[])
    findings = agent_topology_lint(_recipe(dag))
    assert_finding_status(findings, "dag.exactly_one_llm_node", "FAIL")


def test_two_llm_nodes_fails() -> None:
    dag = Dag(
        nodes=[
            Node(id="llm-1", type=NodeType.LLM_STEP, params={}),
            Node(id="llm-2", type=NodeType.LLM_STEP, params={}),
        ],
        edges=[],
    )
    findings = agent_topology_lint(_recipe(dag))
    assert_finding_status(findings, "dag.exactly_one_llm_node", "FAIL")


def test_two_kb_retrieve_nodes_fails() -> None:
    dag = Dag(
        nodes=[
            Node(id="llm-1", type=NodeType.LLM_STEP, params={}),
            Node(id="kb-1", type=NodeType.KB_RETRIEVE, params={}),
            Node(id="kb-2", type=NodeType.KB_RETRIEVE, params={}),
        ],
        edges=[Edge(from_="kb-1", to="llm-1"), Edge(from_="kb-2", to="llm-1")],
    )
    findings = agent_topology_lint(_recipe(dag))
    assert_finding_status(findings, "dag.at_most_one_kb_retrieve_node", "FAIL")


def test_kb_retrieve_not_connected_to_llm_fails() -> None:
    dag = Dag(
        nodes=[
            Node(id="llm-1", type=NodeType.LLM_STEP, params={}),
            Node(id="kb-1", type=NodeType.KB_RETRIEVE, params={}),
        ],
        edges=[],
    )
    findings = agent_topology_lint(_recipe(dag))
    assert_finding_status(findings, "dag.kb_retrieve_connects_to_llm", "FAIL")


def test_tool_call_not_connected_to_llm_fails() -> None:
    dag = Dag(
        nodes=[
            Node(id="llm-1", type=NodeType.LLM_STEP, params={}),
            Node(id="tool-1", type=NodeType.TOOL_CALL, params={"tool": "calculator"}),
        ],
        edges=[],
    )
    findings = agent_topology_lint(_recipe(dag))
    assert_finding_status(findings, "dag.tool_call_connects_to_llm", "FAIL")


def test_tool_call_blank_tool_fails() -> None:
    dag = Dag(
        nodes=[
            Node(id="llm-1", type=NodeType.LLM_STEP, params={}),
            Node(id="tool-1", type=NodeType.TOOL_CALL, params={}),
        ],
        edges=[Edge(from_="tool-1", to="llm-1")],
    )
    findings = agent_topology_lint(_recipe(dag))
    assert_finding_status(findings, "dag.tool_call_has_non_blank_tool", "FAIL")


def test_tool_call_duplicate_tool_fails() -> None:
    dag = Dag(
        nodes=[
            Node(id="llm-1", type=NodeType.LLM_STEP, params={}),
            Node(id="tool-1", type=NodeType.TOOL_CALL, params={"tool": "calculator"}),
            Node(id="tool-2", type=NodeType.TOOL_CALL, params={"tool": "calculator"}),
        ],
        edges=[Edge(from_="tool-1", to="llm-1"), Edge(from_="tool-2", to="llm-1")],
    )
    findings = agent_topology_lint(_recipe(dag))
    assert_finding_status(findings, "dag.tool_call_no_duplicate_tools", "FAIL")


def test_edge_between_two_tool_call_nodes_fails() -> None:
    dag = Dag(
        nodes=[
            Node(id="llm-1", type=NodeType.LLM_STEP, params={}),
            Node(id="tool-1", type=NodeType.TOOL_CALL, params={"tool": "calculator"}),
            Node(id="tool-2", type=NodeType.TOOL_CALL, params={"tool": "current_datetime"}),
        ],
        edges=[
            Edge(from_="tool-1", to="llm-1"),
            Edge(from_="tool-2", to="llm-1"),
            Edge(from_="tool-1", to="tool-2"),
        ],
    )
    findings = agent_topology_lint(_recipe(dag))
    assert_finding_status(findings, "dag.edges_are_llm_hub_spokes_only", "FAIL")


def test_edge_to_nonexistent_node_fails() -> None:
    dag = Dag(
        nodes=[Node(id="llm-1", type=NodeType.LLM_STEP, params={})],
        edges=[Edge(from_="llm-1", to="ghost")],
    )
    findings = agent_topology_lint(_recipe(dag))
    assert_finding_status(findings, "dag.edges_are_llm_hub_spokes_only", "FAIL")


def test_enforce_agent_topology_raises_on_first_failure() -> None:
    dag = Dag(nodes=[], edges=[])
    with pytest.raises(ValueError, match="agent_topology_lint: dag.exactly_one_llm_node"):
        enforce_agent_topology(_recipe(dag))
