"""AgentConfig Builder & Sample Recipe Generator for Day 3 — SWE (Thiệu Quang Minh).

Cung cấp các hàm đóng gói dữ liệu Form UI thành đối tượng AgentConfig chuẩn v0
và khởi tạo bản Recipe thử nghiệm 3-node (kb-retrieve -> llm-step -> tool-call -> end)
để wiring sang Interpreter của Engine.
"""

from __future__ import annotations

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


def build_agent_config(
    instructions: str,
    model: str,
    tool_whitelist: list[str],
) -> AgentConfig:
    """Tạo đối tượng AgentConfig chuẩn Pydantic v0 từ dữ liệu Form UI nhập vào.

    Args:
        instructions (str): Câu lệnh prompt dặn dò AI Agent.
        model (str): Tên mô hình LLM được chọn (ví dụ: 'gemini-2.5-flash').
        tool_whitelist (list[str]): Danh sách các tên tool được phép gọi (whitelist).

    Returns:
        AgentConfig: Đối tượng AgentConfig đã được validate tính hợp lệ qua Pydantic schema.

    Raises:
        ValueError: Nếu bất kỳ trường dữ liệu nào bị thiếu hoặc không đúng kiểu dữ liệu str/list.
    """
    return AgentConfig(
        instructions=instructions,
        model=model,
        tool_whitelist=tool_whitelist,
    )


def create_sample_recipe_d3() -> Recipe:
    """Khởi tạo một đối tượng Recipe thử nghiệm Ngày 3 chứa chuỗi 3 Node tuần tự.

    Cấu trúc chuỗi node:
    - node_1 (kb-retrieve): Tìm kiếm thông tin từ KB
    - node_2 (llm-step): Xử lý câu trả lời bằng LLM
    - node_3 (tool-call): Gọi tool truy vấn tri thức
    - node_4 (end): Kết thúc luồng thực thi

    Returns:
        Recipe: Bản Recipe hoàn chỉnh đúng chuẩn Contract v0 (R-SPEC A1#1).
    """
    # 1. Tạo agent_config từ dữ liệu Form
    config = build_agent_config(
        instructions="Hãy tra cứu tài liệu Callisto và trả lời thắc mắc của người dùng.",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search"],
    )

    # 2. Định nghĩa 3 Node chính + Node END
    nodes = [
        Node(id="node_1", type=NodeType.KB_RETRIEVE, params={"query": "Callisto policy"}),
        Node(id="node_2", type=NodeType.LLM_STEP, params={"temperature": 0.0}),
        Node(id="node_3", type=NodeType.TOOL_CALL, params={"tool": "kb_search"}),
        Node(id="node_4", type=NodeType.END, params={}),
    ]

    # 3. Định nghĩa các Edges nối tuần tự: node_1 -> node_2 -> node_3 -> node_4
    edges = [
        Edge(from_="node_1", to="node_2"),
        Edge(from_="node_2", to="node_3"),
        Edge(from_="node_3", to="node_4"),
    ]

    # 4. Gom thành đối tượng Recipe v0
    return Recipe(
        agent_id="agent_demo_d3",
        tenant="ankor",
        agent_config=config,
        dag=Dag(nodes=nodes, edges=edges),
        kb_binding=KbBinding(kb_id="kb_callisto", scope="public"),
        golden_set_ref="golden_set_1",
        scorecard_threshold=ScorecardThreshold(success=0.9, citation_accuracy=0.95),
    )
