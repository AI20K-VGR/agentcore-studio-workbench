"""Recipe Builder module for Workbench (SWE owner — Thiệu Quang Minh).

Provides unified recipe building functions for Day 4, Day 6, and dynamic DAG recipes.

`create_sample_recipe_d3`/alias `create_recipe_d3` (Day 3 precursor) removed Day 21 — kiểm kê
toàn repo xác nhận 0 caller ngoài `packages/workbench` (không production, không submodule khác),
hành vi là tập con thật sự của `create_recipe_d4`. Xem `docs/design-notes/
swe-day21-user-flow-diagrams.md` cho evidence đầy đủ.
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
BOREA_ID = UUID("b0000000-0000-0000-0000-000000000001")

# Hai tenant nghiệp vụ thật đã biết trước — dùng để giới hạn phạm vi của guard "roles không
# được rỗng" bên dưới, KHÔNG dùng để cross-check slug (xem docstring _parse_kb_scope: PR #16
# từng làm vậy rồi bị revert ở kit#92/workbench#17 vì đụng cả 2 quadrant khác — INV-1 test của
# kb cố tình dựng recipe với slug/tenant_id lệch nhau, và eval-harness của app dùng slug
# placeholder "t" bất kể tenant_id là tổng hợp hay thật).
_KNOWN_TENANT_IDS: frozenset[UUID] = frozenset({ANKOR_ID, BOREA_ID})


def _parse_kb_scope(scope: str, tenant_id: UUID) -> list[str]:
    """Parse chuỗi scope KB thành ``section_roles``, chỉ validate CẤU TRÚC.

    Split ``kb_binding.scope`` (vd: ``"ankor/public, hr"``) thành ``section_roles``.

    Format hợp lệ: ``"<tenant_slug>/<role1>, <role2>, ..."`` — ``tenant_slug`` KHÔNG được
    cross-check với ``tenant_id`` (đã bỏ ở kit#92/workbench#17). Bản gốc (workbench#16) chặn
    slug ngoài ``{ankor, borea}`` hoặc lệch với ``tenant_id``, đúng ý P1 review gốc của
    dholmes0207 — nhưng recipe-build-time là SAI CHỖ để chặn việc đó:

    - ``packages/kb/tests/test_spine_live.py`` dựng recipe với ``tenant_id`` (attacker khai)
      lệch CÓ CHỦ ĐÍCH với slug trong scope, để kiểm INV-1 (session phải thắng chứ không phải
      recipe tự khai) — chặn ở build-time thì bài test không bao giờ chạy tới đoạn nó kiểm.
    - ``apps/studio/src/studio_app/eval_adapter.py`` dùng slug placeholder ``"t"`` cho MỌI
      tenant (kể cả ankor/borea thật trong test Postgres) — không có quy ước nào để phân biệt
      "t" cố ý với một lỗi gõ thật.

    Việc bắt lỗi gõ-sai-slug/lệch-tenant giờ thuộc trách nhiệm của tầng khác (nơi thật sự
    dùng ``tenant_id`` để query, vd: session-resolve ở ``tenant_wall.py`` — session luôn thắng
    recipe tự khai, đó là INV-1), không phải ở đây nữa.

    Section-role values không được validate ở đây — workbench không own KB schema.
    Role không tồn tại sẽ bị reject bởi ``kb.search`` tại query time với lỗi rõ ràng.

    Raises:
        ValueError: Nếu scope rỗng, không có dấu ``/``, slug rỗng, hoặc — khi ``tenant_id``
            là 1 trong 2 tenant nghiệp vụ thật (``ANKOR_ID``/``BOREA_ID``) — phần roles rỗng.
    """
    if not scope or not scope.strip():
        raise ValueError(f"scope không được rỗng, nhận được: {scope!r}")

    if "/" not in scope:
        raise ValueError(f"scope phải có dạng '<tenant>/<roles>', không có '/' trong: {scope!r}")

    tenant_slug, roles_part = scope.split("/", 1)
    tenant_slug = tenant_slug.strip()

    if not tenant_slug:
        raise ValueError(f"Tenant slug rỗng trong scope: {scope!r}")

    section_roles = [r.strip() for r in roles_part.split(",") if r.strip()]

    if not section_roles and tenant_id in _KNOWN_TENANT_IDS:
        # Rỗng có chủ đích trên tenant tổng hợp/per-test (vd: eval-harness của app, KHÓA B8b)
        # được đi qua nguyên trạng — downstream kb.search fail-closed trên roles=[]. Chỉ tenant
        # nghiệp vụ thật mới bị chặn ở đây: "ankor/" gần như chắc chắn là quên gõ role.
        raise ValueError(f"Phần roles trong scope rỗng: {scope!r}. Cần ít nhất một role (vd: 'public', 'hr').")

    return section_roles


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
    golden_set_ref: str = "callisto-golden-30-v1",
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

    # `_parse_kb_scope` chỉ validate CẤU TRÚC của `scope` (bắt lỗi gõ sai sớm lúc build) — giá trị
    # trả về không còn cần đưa vào `node.params` nữa: `interpreter.run()` luôn ghi đè
    # `tenant_id`/`section_roles` của node `kb-retrieve` bằng `session_context` (D8/D17, #111),
    # nên bất kỳ giá trị nào khai ở đây đều bị bỏ qua tại thời điểm chạy thật.
    _parse_kb_scope(scope, t_id)

    nodes = [
        Node(
            id="n1",
            type=NodeType.KB_RETRIEVE,
            params={
                "query": query,
                "top_k": 3,
            },
        ),
        Node(id="n2", type=NodeType.LLM_STEP, params={"temperature": 0.0}),
        Node(id="n3", type=NodeType.TOOL_CALL, params={"tool": "kb_search"}),
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
        golden_set_ref="callisto-golden-30-v1",
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
    golden_set_ref: str = "callisto-golden-30-v1",
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

    # `_parse_kb_scope` chỉ validate CẤU TRÚC của `scope` (bắt lỗi gõ sai sớm lúc build) — giá trị
    # trả về không còn cần đưa vào `node.params` nữa: `interpreter.run()` luôn ghi đè
    # `tenant_id`/`section_roles` của node `kb-retrieve` bằng `session_context` (D8/D17, #111),
    # nên bất kỳ giá trị nào khai ở đây đều bị bỏ qua tại thời điểm chạy thật.
    _parse_kb_scope(scope, t_id)

    nodes = [
        Node(
            id="n1",
            type=NodeType.KB_RETRIEVE,
            params={
                "query": query,
                "top_k": 3,
            },
        ),
        Node(id="n2", type=NodeType.LLM_STEP, params={"temperature": 0.0}),
        Node(id="n4", type=NodeType.END, params={}),
    ]

    edges = [
        Edge(from_="n1", to="n2"),
        Edge(from_="n2", to="n4"),
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
    "BOREA_ID",
    "_parse_kb_scope",
    "build_agent_config",
    "create_dynamic_recipe",
    "create_recipe_d4",
    "create_recipe_d6",
]
