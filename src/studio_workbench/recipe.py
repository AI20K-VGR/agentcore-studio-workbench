"""Recipe Builder module for Workbench (SWE owner — Thiệu Quang Minh).

Provides the recipe building function for dynamic DAG recipes.

`create_sample_recipe_d3`/alias `create_recipe_d3` (Day 3 precursor) removed Day 21 — kiểm kê
toàn repo xác nhận 0 caller ngoài `packages/workbench` (không production, không submodule khác),
hành vi là tập con thật sự của `create_recipe_d4`. Xem `docs/design-notes/
swe-day21-user-flow-diagrams.md` cho evidence đầy đủ.

`create_recipe_d6` (Day 6 Form-Feed builder) removed 2026-08-24 (workbench#31 follow-up cleanup)
— kiểm kê toàn repo xác nhận 0 caller production (`apps/studio`, `packages/kb`), chỉ còn tự tham
chiếu trong test của chính package + 1 script rời `scripts/smoke_eval_d6.py` (gốc kit,
đóng băng từ D7, không nằm trong CI nào).

`create_recipe_d4`/`_parse_kb_scope` removed 2026-08-24 (workbench#41, kit#218) — sau khi
`create_recipe` (đổi tên từ `create_dynamic_recipe`) hardcode `kb_binding` cố định, builder D4
(nhận `kb_id`/`scope`/`query` làm tham số thật + validate cấu trúc `scope` qua `_parse_kb_scope`)
không còn caller production nào (`eval_adapter.py::certified_recipe()` chuyển sang `create_recipe`
với DAG cố định). `create_recipe` là builder Form-Feed thật duy nhất còn lại.

`create_recipe` (đổi tên từ `create_dynamic_recipe`): `model`, `kb_id`/`scope`,
`success_threshold`/`citation_accuracy_threshold` không còn là tham số động — cố định trong
hàm (quyết định nền tảng, không cho client tùy chỉnh). `temperature` là tham số động mới,
input thật của người dùng, forward vào `AgentConfig`.
"""

from __future__ import annotations

from uuid import UUID

from studio_contracts import (
    AgentConfig,
    Dag,
    Edge,
    KbBinding,
    Node,
    Recipe,
    ScorecardThreshold,
)

ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")
BOREA_ID = UUID("b0000000-0000-0000-0000-000000000001")


def build_agent_config(
    system_prompt: str,
    model: str,
    tool_whitelist: list[str],
    temperature: float = 0.7,
) -> AgentConfig:
    """Tạo đối tượng AgentConfig chuẩn Pydantic v0 từ dữ liệu Form UI nhập vào."""
    return AgentConfig(
        system_prompt=system_prompt,
        model=model,
        tool_whitelist=tool_whitelist,
        temperature=temperature,
    )


# Quyết định nền tảng cố định (không cho client tùy chỉnh) cho `create_recipe`: model, KB
# binding, và ngưỡng eval không còn là tham số động — xem docstring module ở trên.
_DEFAULT_MODEL = "gemini-2.5-flash"
_DEFAULT_KB_ID = "kb-callisto-v1"
_DEFAULT_SCOPE = "ankor/public"
_DEFAULT_SUCCESS_THRESHOLD = 0.9
_DEFAULT_CITATION_ACCURACY_THRESHOLD = 0.95


def create_recipe(
    agent_id: str,
    tenant_id: UUID | str,
    system_prompt: str,
    tool_whitelist: list[str],
    nodes: list[Node],
    edges: list[Edge],
    temperature: float = 0.7,
    golden_set_ref: str = "callisto-golden-30-v1",
    success_threshold: float = _DEFAULT_SUCCESS_THRESHOLD,
    citation_accuracy_threshold: float = _DEFAULT_CITATION_ACCURACY_THRESHOLD,
) -> Recipe:
    """Khởi tạo một Recipe động hoàn toàn từ danh sách Nodes và Edges do UI kéo thả truyền vào.

    Hỗ trợ số lượng node ngẫu nhiên (2 node, 3 node, hay N node) kết nối tùy ý dưới dạng đồ thị DAG.

    `model` và KB binding (`kb_id`/`scope`) là quyết định nền tảng cố định — không nhận từ client.
    `temperature` là input thật của người dùng.

    ## Ngưỡng eval: từ cố định thành nhận-được (mặc định không đổi)

    `kit#212/workbench#39` chốt hai ngưỡng này là hằng số nền tảng. Quyết định đó đứng được khi bộ
    golden là bản viết tay 30 case; nó không còn đứng khi bộ được **sinh máy từ tài liệu người dùng
    upload**, cỡ 10–20 case: ở mức đó một case trượt ăn 5–10% của một trục, nên `0.95` trên trục
    citation nghĩa là **không được sai case nào**. Đo được: một agent trả lời đúng 10/11 và giữ hàng
    rào 3/3 vẫn bị chặn publish, không có mặt phẳng nào để chỉnh.

    Nới được mà không hạ chuẩn an toàn là vì hàng rào bảo mật ĐÃ tách thành cổng riêng
    (`evalhub.compute_scorecard`: một case `fail_leak` ⇒ FAIL bất kể tỷ lệ). Trước bản vá đó, hạ
    ngưỡng ở đây đồng nghĩa hạ luôn hàng rào — case bẫy gộp chung vào `success_rate`, nên hai trục
    hoàn toàn khác nhau bị buộc vào một con số.

    Mặc định giữ nguyên `_DEFAULT_*`, nên mọi call-site không truyền vẫn ra recipe y hệt trước.
    """
    t_id = tenant_id if isinstance(tenant_id, UUID) else UUID(tenant_id)

    config = build_agent_config(
        system_prompt=system_prompt,
        model=_DEFAULT_MODEL,
        tool_whitelist=tool_whitelist,
        temperature=temperature,
    )

    kb_bind = KbBinding(kb_id=_DEFAULT_KB_ID, scope=_DEFAULT_SCOPE)

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
    "build_agent_config",
    "create_recipe",
]
