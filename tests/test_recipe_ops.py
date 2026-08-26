"""`recipe_ops.with_query`/`without_query` spec tests (PR#27 review gap — module shipped with
ZERO test coverage even though its entire reason to exist is fixing a real behavioral drift bug:
`apps/studio`'s `chat.py::_with_query` patches EVERY `kb-retrieve` node while `eval_adapter.py`'s
own copy patches only the FIRST one. The tests below exist specifically to pin the semantics this
module is supposed to guarantee once `apps/studio` is wired to import it, so that regression back
to "first node only" (or any other silent drift) fails loudly here first.
"""

from __future__ import annotations

from uuid import UUID

from studio_contracts import AgentConfig, Dag, Edge, KbBinding, Node, NodeType, Recipe, ScorecardThreshold

from studio_workbench.recipe_ops import with_kb_search_whitelisted, with_query, without_query

ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")


def _recipe(nodes: list[Node], edges: list[Edge], tool_whitelist: list[str] | None = None) -> Recipe:
    return Recipe(
        agent_id="agent-1",
        tenant_id=ANKOR_ID,
        agent_config=AgentConfig(
            system_prompt="Answer from KB only.", model="gpt-4o-mini", tool_whitelist=tool_whitelist or []
        ),
        dag=Dag(nodes=nodes, edges=edges),
        kb_binding=KbBinding(kb_id="kb-1", scope="ankor/public"),
        golden_set_ref="golden-set-1",
        scorecard_threshold=ScorecardThreshold(success=0.9, citation_accuracy=0.95),
    )


def test_with_query_patches_every_kb_retrieve_node() -> None:
    """KHÓA: đây là bug chính module này tồn tại để fix — recipe có 2+ node `kb-retrieve` phải
    được bơm `query` vào TẤT CẢ, không chỉ node đầu tiên (hành vi cũ, sai của `eval_adapter.py`)."""
    recipe = _recipe(
        nodes=[
            Node(id="n1", type=NodeType.KB_RETRIEVE, params={"kb_id": "a"}),
            Node(id="n2", type=NodeType.KB_RETRIEVE, params={"kb_id": "b"}),
            Node(id="n3", type=NodeType.END, params={}),
        ],
        edges=[Edge(from_="n1", to="n2", when=None), Edge(from_="n2", to="n3", when=None)],
    )
    patched = with_query(recipe, "câu hỏi của người dùng")

    assert patched.dag.nodes[0].params["query"] == "câu hỏi của người dùng"
    assert patched.dag.nodes[1].params["query"] == "câu hỏi của người dùng"


def test_with_query_leaves_non_kb_retrieve_nodes_untouched() -> None:
    """KHÓA: node không phải `kb-retrieve` (ở đây: `end`) đi qua nguyên vẹn — không được nhận
    `params["query"]`, và cũng không bị đổi identity/nội dung khác."""
    recipe = _recipe(
        nodes=[
            Node(id="n1", type=NodeType.KB_RETRIEVE, params={}),
            Node(id="n2", type=NodeType.END, params={"foo": "bar"}),
        ],
        edges=[Edge(from_="n1", to="n2", when=None)],
    )
    patched = with_query(recipe, "q")

    assert "query" not in patched.dag.nodes[1].params
    assert patched.dag.nodes[1].params == {"foo": "bar"}


def test_with_query_and_without_query_are_noop_on_zero_kb_retrieve_nodes() -> None:
    """KHÓA: DAG hợp lệ không có node `kb-retrieve` nào (chỉ `end`) không được raise, và trả về
    nội dung không đổi — docstring `_map_kb_retrieve_params` hứa điều này, test này khoá lại."""
    recipe = _recipe(nodes=[Node(id="n1", type=NodeType.END, params={})], edges=[])

    with_result = with_query(recipe, "q")
    without_result = without_query(recipe)

    assert with_result.dag.nodes[0].params == {}
    assert without_result.dag.nodes[0].params == {}


def test_without_query_removes_key_entirely_not_empty_string() -> None:
    """KHÓA: `without_query` phải XOÁ hẳn key `"query"`, không set thành `""` — 2 giá trị này ra
    2 chuỗi byte JSON khác nhau, và `publish.recipe_hash()` băm đúng chuỗi đó (xem docstring
    `without_query`). Set `""` thay vì xoá key sẽ làm hash lệch mà không ai để ý."""
    recipe = _recipe(
        nodes=[Node(id="n1", type=NodeType.KB_RETRIEVE, params={"query": "câu hỏi cũ", "kb_id": "a"})],
        edges=[],
    )
    stripped = without_query(recipe)

    assert "query" not in stripped.dag.nodes[0].params
    assert stripped.dag.nodes[0].params == {"kb_id": "a"}


def test_without_query_is_noop_when_query_key_absent() -> None:
    """KHÓA: gọi `without_query` trên recipe vốn không có `query` không raise và không đổi gì."""
    recipe = _recipe(nodes=[Node(id="n1", type=NodeType.KB_RETRIEVE, params={"kb_id": "a"})], edges=[])
    stripped = without_query(recipe)
    assert stripped.dag.nodes[0].params == {"kb_id": "a"}


def test_with_query_does_not_mutate_original_recipe() -> None:
    """KHÓA lời hứa "does not mutate `recipe`" trong docstring — `recipe.dag.nodes[0].params` của
    object GỐC phải giữ nguyên sau khi gọi `with_query` trên nó."""
    recipe = _recipe(nodes=[Node(id="n1", type=NodeType.KB_RETRIEVE, params={"kb_id": "a"})], edges=[])
    original_params = dict(recipe.dag.nodes[0].params)

    with_query(recipe, "q")

    assert recipe.dag.nodes[0].params == original_params
    assert "query" not in recipe.dag.nodes[0].params


def test_without_query_does_not_mutate_original_recipe() -> None:
    """Đối chứng cho `without_query` — cùng lời hứa, cùng cần khoá."""
    recipe = _recipe(
        nodes=[Node(id="n1", type=NodeType.KB_RETRIEVE, params={"query": "q", "kb_id": "a"})],
        edges=[],
    )
    original_params = dict(recipe.dag.nodes[0].params)

    without_query(recipe)

    assert recipe.dag.nodes[0].params == original_params


def test_with_kb_search_whitelisted_adds_when_kb_retrieve_node_present() -> None:
    """KHÓA engine#49 review F1 — backfill: recipe có node `kb-retrieve` nhưng `tool_whitelist`
    thiếu `kb_search` (hình dạng MỌI recipe publish TRƯỚC PR #57 — luật `tool_whitelist.no_kb_search`
    cũ từ chối mọi whitelist có `kb_search`) phải nhận thêm `kb_search`, giữ nguyên tool khác."""
    recipe = _recipe(
        nodes=[Node(id="n1", type=NodeType.KB_RETRIEVE, params={}), Node(id="n2", type=NodeType.LLM_STEP, params={})],
        edges=[Edge(from_="n1", to="n2", when=None)],
        tool_whitelist=["calculator"],
    )
    patched = with_kb_search_whitelisted(recipe)
    assert patched.agent_config.tool_whitelist == ["kb_search", "calculator"]


def test_with_kb_search_whitelisted_noop_without_kb_retrieve_node() -> None:
    """KHÓA: recipe KHÔNG có node `kb-retrieve` nào (chatbot thuần) không được nhận `kb_search` —
    backfill chỉ vá đúng agent thật sự có nối KB, không mở rộng phạm vi tool cho agent khác."""
    recipe = _recipe(
        nodes=[Node(id="n1", type=NodeType.LLM_STEP, params={})],
        edges=[],
        tool_whitelist=["calculator"],
    )
    patched = with_kb_search_whitelisted(recipe)
    assert patched.agent_config.tool_whitelist == ["calculator"]


def test_with_kb_search_whitelisted_noop_when_already_present() -> None:
    """KHÓA: idempotent — recipe đã có `kb_search` trong whitelist (agent publish SAU PR #57) không
    bị nhân đôi. Cần thiết để script backfill chạy lại nhiều lần an toàn (không chỉ chạy đúng 1 lần)."""
    recipe = _recipe(
        nodes=[Node(id="n1", type=NodeType.KB_RETRIEVE, params={})],
        edges=[],
        tool_whitelist=["kb_search", "calculator"],
    )
    patched = with_kb_search_whitelisted(recipe)
    assert patched.agent_config.tool_whitelist == ["kb_search", "calculator"]


def test_with_kb_search_whitelisted_does_not_mutate_original_recipe() -> None:
    """Cùng lời hứa 'does not mutate' với `with_query`/`without_query` — `Recipe`/`AgentConfig` đều
    `frozen=True` nên phải trả object MỚI, recipe gốc không đổi."""
    recipe = _recipe(
        nodes=[Node(id="n1", type=NodeType.KB_RETRIEVE, params={})],
        edges=[],
        tool_whitelist=["calculator"],
    )
    with_kb_search_whitelisted(recipe)
    assert recipe.agent_config.tool_whitelist == ["calculator"]


def test_with_query_deep_copies_nested_params_not_shared_with_original() -> None:
    """KHÓA fix shallow-copy: `params` có thể chứa `dict`/`list` lồng nhau (kiểu `dict[str,
    object]`, không có schema con) — mutate cấu trúc lồng trong recipe TRẢ VỀ không được rò rỉ
    ngược lại recipe GỐC. Trước bản vá `copy.deepcopy`, `dict(node.params)` chỉ copy nông, nên
    `filters` bên dưới sẽ là CÙNG object giữa 2 recipe."""
    recipe = _recipe(
        nodes=[Node(id="n1", type=NodeType.KB_RETRIEVE, params={"kb_id": "a", "filters": {"scope": "old"}})],
        edges=[],
    )
    patched = with_query(recipe, "q")

    # Mutate cấu trúc lồng trong recipe TRẢ VỀ, không phải recipe gốc.
    patched.dag.nodes[0].params["filters"]["scope"] = "new"  # type: ignore[index]

    assert recipe.dag.nodes[0].params["filters"]["scope"] == "old"  # type: ignore[index]
