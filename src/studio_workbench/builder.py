"""Recipe Builder module for Workbench (SWE owner — Thiệu Quang Minh).

Provides unified recipe building functions for Day 3, Day 4, Day 6, and dynamic DAG recipes.
"""

from __future__ import annotations

from uuid import UUID

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

ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")


def build_agent_config(
    instructions: str,
    model: str,
    tool_whitelist: list[str],
) -> AgentConfig:
    """Tạo đối tượng AgentConfig chuẩn Pydantic v0 từ dữ liệu Form UI nhập vào."""
    return AgentConfig(
        instructions=instructions,
        model=model,
        tool_whitelist=tool_whitelist,
    )


def create_dynamic_recipe(
    agent_id: str,
    tenant_id: UUID | str,
    instructions: str,
    model: str,
    tool_whitelist: list[str],
    nodes: list[Node],
    edges: list[Edge],
    kb_id: str | None = None,
    scope: str | None = None,
    golden_set_ref: str = "callisto-smoke-5-v0",
    success_threshold: float = 0.9,
    citation_accuracy_threshold: float = 0.95,
) -> Recipe:
    """Khởi tạo một Recipe động hoàn toàn từ danh sách Nodes và Edges do UI kéo thả truyền vào.

    Hỗ trợ số lượng node ngẫu nhiên (2 node, 3 node, hay N node) kết nối tùy ý dưới dạng đồ thị DAG.
    """
    t_id = tenant_id if isinstance(tenant_id, UUID) else UUID(tenant_id)

    config = build_agent_config(
        instructions=instructions,
        model=model,
        tool_whitelist=tool_whitelist,
    )

    if not kb_id or not scope:
        raise ValueError("Cần truyền đầy đủ 'kb_id' và 'scope' (không rỗng) để tạo Recipe.")

    kb_bind = KbBinding(kb_id=kb_id, scope=scope)

    return Recipe(
        agent_id=agent_id,
        tenant_id=t_id,
        agent_config=config,
        dag=Dag(nodes=nodes, edges=edges),
        kb_binding=kb_bind,
        golden_set_ref=golden_set_ref,
        scorecard_threshold=ScorecardThreshold(
            success=success_threshold,
            citation_accuracy=citation_accuracy_threshold,
        ),
    )


def create_sample_recipe_d3() -> Recipe:
    """Khởi tạo một đối tượng Recipe thử nghiệm Ngày 3 chứa chuỗi 3 Node tuần tự."""
    config = build_agent_config(
        instructions="Hãy tra cứu tài liệu Callisto và trả lời thắc mắc của người dùng.",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search"],
    )

    nodes = [
        Node(id="node_1", type=NodeType.KB_RETRIEVE, params={"query": "Callisto policy"}),
        Node(id="node_2", type=NodeType.LLM_STEP, params={"temperature": 0.0}),
        Node(id="node_3", type=NodeType.TOOL_CALL, params={"tool": "kb_search"}),
        Node(id="node_4", type=NodeType.END, params={}),
    ]

    edges = [
        Edge(from_="node_1", to="node_2"),
        Edge(from_="node_2", to="node_3"),
        Edge(from_="node_3", to="node_4"),
    ]

    return Recipe(
        agent_id="agent_demo_d3",
        tenant_id=ANKOR_ID,
        agent_config=config,
        dag=Dag(nodes=nodes, edges=edges),
        kb_binding=KbBinding(kb_id="kb_callisto", scope="public"),
        golden_set_ref="golden_set_1",
        scorecard_threshold=ScorecardThreshold(success=0.9, citation_accuracy=0.95),
    )


create_recipe_d3 = create_sample_recipe_d3


def create_recipe_d4(
    agent_id: str = "agent-callisto-d4",
    tenant_id: UUID = ANKOR_ID,
    instructions: str = "Tra cứu quy trình và bảo mật Callisto.",
    model: str = "gemini-2.5-flash",
    tool_whitelist: list[str] | None = None,
    kb_id: str = "kb-callisto-v1",
    scope: str = "ankor/public",
    query: str = "Nhân viên xin nghỉ phép cần báo trước bao lâu?",
) -> Recipe:
    """Build a Day 4 Recipe instance containing `kb_binding.{kb_id, scope}`.

    Wiring `recipe -> interpreter` relies on `recipe.kb_binding` to pass
    the declared KB scope to `kb.search`.
    """
    if tool_whitelist is None:
        tool_whitelist = ["kb_search"]

    t_id = tenant_id if isinstance(tenant_id, UUID) else UUID(tenant_id)

    config = build_agent_config(
        instructions=instructions,
        model=model,
        tool_whitelist=tool_whitelist,
    )

    kb_bind = KbBinding(
        kb_id=kb_id,
        scope=scope,
    )

    # Extract tenant and section_roles from scope ("ankor/public")
    if "/" in scope:
        _, roles_part = scope.split("/", 1)
        section_roles = [r.strip() for r in roles_part.split(",") if r.strip()]
    else:
        section_roles = [scope] if scope else ["public"]

    nodes = [
        Node(
            id="n1",
            type=NodeType.KB_RETRIEVE,
            params={
                "query": query,
                "tenant_id": t_id,
                "section_roles": section_roles,
                "top_k": 3,
            },
        ),
        Node(id="n2", type=NodeType.LLM_STEP, params={"temperature": 0.0}),
        Node(
            id="n3",
            type=NodeType.TOOL_CALL,
            params={"tool": tool_whitelist[0] if tool_whitelist else "kb_search"},
        ),
        Node(id="n4", type=NodeType.END, params={}),
    ]

    edges = [
        Edge(from_="n1", to="n2"),
        Edge(from_="n2", to="n3"),
        Edge(from_="n3", to="n4"),
    ]

    return Recipe(
        agent_id=agent_id,
        tenant_id=t_id,
        agent_config=config,
        dag=Dag(nodes=nodes, edges=edges),
        kb_binding=kb_bind,
        golden_set_ref="callisto-smoke-5-v0",
        scorecard_threshold=ScorecardThreshold(success=0.9, citation_accuracy=0.95),
    )


def create_recipe_d6(
    agent_id: str,
    tenant_id: UUID,
    instructions: str,
    model: str,
    tool_whitelist: list[str],
    kb_id: str,
    scope: str,
    query: str,
    golden_set_ref: str = "callisto-smoke-5-v0",
    success_threshold: float = 0.9,
    citation_accuracy_threshold: float = 0.95,
) -> Recipe:
    """Build a Day 6 dynamic Recipe instance driven 100% by user inputs.

    All core parameters (`agent_id`, `tenant_id`, `instructions`, `model`,
    `tool_whitelist`, `kb_id`, `scope`, `query`) are required positional/keyword
    arguments with NO hardcoded default values.
    """
    t_id = tenant_id if isinstance(tenant_id, UUID) else UUID(tenant_id)

    config = build_agent_config(
        instructions=instructions,
        model=model,
        tool_whitelist=tool_whitelist,
    )

    kb_bind = KbBinding(
        kb_id=kb_id,
        scope=scope,
    )

    # Extract section_roles from scope (e.g. "ankor/public" -> section_roles=["public"])
    if "/" in scope:
        _, roles_part = scope.split("/", 1)
        section_roles = [r.strip() for r in roles_part.split(",") if r.strip()]
    else:
        section_roles = [scope] if scope else ["public"]

    nodes = [
        Node(
            id="n1",
            type=NodeType.KB_RETRIEVE,
            params={
                "query": query,
                "tenant_id": t_id,
                "section_roles": section_roles,
                "top_k": 3,
            },
        ),
        Node(id="n2", type=NodeType.LLM_STEP, params={"temperature": 0.0}),
        Node(
            id="n3",
            type=NodeType.TOOL_CALL,
            params={"tool": tool_whitelist[0] if tool_whitelist else "kb_search"},
        ),
        Node(id="n4", type=NodeType.END, params={}),
    ]

    edges = [
        Edge(from_="n1", to="n2"),
        Edge(from_="n2", to="n3"),
        Edge(from_="n3", to="n4"),
    ]

    return Recipe(
        agent_id=agent_id,
        tenant_id=t_id,
        agent_config=config,
        dag=Dag(nodes=nodes, edges=edges),
        kb_binding=kb_bind,
        golden_set_ref=golden_set_ref,
        scorecard_threshold=ScorecardThreshold(
            success=success_threshold,
            citation_accuracy=citation_accuracy_threshold,
        ),
    )


__all__ = [
    "ANKOR_ID",
    "build_agent_config",
    "create_dynamic_recipe",
    "create_recipe_d3",
    "create_recipe_d4",
    "create_recipe_d6",
    "create_sample_recipe_d3",
]
