"""Wiring D12 (issue kit#87) — canvas `apps/web` → `Recipe` → `graph_lint`, fail-closed.

Fixture `fixtures/canvas_export_d12.json` KHÔNG phải JSON gõ tay: nó do `pnpm emit-fixture`
(`apps/web/scripts/emit-fixture.ts`) sinh ra từ chính `buildRecipe()` + `sampleGraph()` mà canvas
dùng. Đó là điểm mấu chốt của cả file test này — nếu fixture là bản chép tay, nó sẽ đứng yên khi
canvas đổi hình dạng và test vẫn xanh trong khi khe web↔Python đã gãy. Sinh từ code thì canvas
đổi mà quên chạy lại `emit-fixture` sẽ lộ ra ở diff, còn canvas đổi ra hình dạng contract từ chối
thì lộ ra ở chính test này.

Hai tầng được khoá ở đây:
1. **Contract** — output canvas parse được qua `studio_contracts.Recipe` (đủ 7 field, đúng kiểu).
2. **Graph-lint** — output đó qua sạch cả 7 luật (4 luật D11 + 3 luật D12/kit#87 theo yêu cầu
   AIE-1: start-node, outgoing-edge cap, walk kết ở `end`); mỗi luật bị vi phạm thì bị chặn thật.
   File này chỉ pin lại 4 luật D11 qua đường canvas — 3 luật mới có bộ test riêng trong
   `test_graph_lint.py` (đủ hơn: cần case multi-start, không chỉ zero-start).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from studio_contracts import NodeType

from studio_workbench.canvas import recipe_from_canvas

FIXTURE = Path(__file__).parent / "fixtures" / "canvas_export_d12.json"


def _payload() -> dict[str, Any]:
    """Đọc lại fixture MỖI lần gọi + deepcopy — các test negative bên dưới sửa payload tại chỗ,
    dùng chung 1 dict sẽ khiến test này làm hỏng input của test kia."""
    return copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_canvas_export_passes_contract_and_lint() -> None:
    """KHÓA: recipe do canvas 6-node xuất ra đi lọt qua `Recipe` + `graph_lint` sạch.

    Đây là DoD D12 ô 1 ("canvas sinh recipe đúng schema") — và là khe mà bản form D4 cũ CHƯA
    từng đi qua: nó xuất `tenant` (slug) thay vì `tenant_id` (UUID) và thiếu hẳn 2 field bắt
    buộc, nên chưa bao giờ parse nổi thành `Recipe` (xem `test_legacy_form_shape_is_rejected`).
    """
    recipe = recipe_from_canvas(_payload())

    assert recipe.agent_id == "agent-callisto-d12"
    # tenant_id phải là UUID thật, không phải slug — đây là điểm D-13 mà form cũ trượt.
    assert recipe.tenant_id == UUID("a0000000-0000-0000-0000-000000000001")
    assert recipe.golden_set_ref == "callisto-2.0-golden-30-v1"
    assert recipe.scorecard_threshold.success == pytest.approx(0.9)


def test_canvas_nodes_stay_inside_the_closed_six() -> None:
    """KHÓA: palette đóng — mọi node canvas sinh ra đều ∈ 6 `NodeType`, và edge dùng alias `from`
    (F12) đúng như contract khai, chứ không phải tên field Python `from_`."""
    payload = _payload()

    assert {node["type"] for node in payload["dag"]["nodes"]} <= {t.value for t in NodeType}
    assert all("from" in edge and "to" in edge for edge in payload["dag"]["edges"])

    recipe = recipe_from_canvas(payload)
    assert [edge.from_ for edge in recipe.dag.edges] == ["n1", "n2"]


# ---------------------------------------------------------------------------
# Negative — 4 luật graph-lint, mỗi luật sửa ĐÚNG 1 chỗ trên fixture happy
# ---------------------------------------------------------------------------


def test_rule_1_node_outside_closed_six_is_rejected() -> None:
    """KHÓA luật 1: node type ngoài 6 loại bị chặn. Canvas tự nó không tạo nổi node như vậy
    (palette đóng), nhưng nút Import cho dán JSON tuỳ ý — đó là đường vào mà luật 1 canh."""
    payload = _payload()
    payload["dag"]["nodes"][0]["type"] = "not-a-real-type"

    with pytest.raises(ValueError):
        recipe_from_canvas(payload)


def test_rule_2_cycle_is_rejected() -> None:
    """KHÓA luật 2: thêm đúng 1 cạnh `n4 -> n2` biến DAG thành có chu trình (n2->n3->n4->n2)
    → bị chặn. Recipe vẫn hợp lệ hoàn toàn về KIỂU (Pydantic cho qua) — chỉ `graph_lint` mới
    bắt được, đúng lý do nó tồn tại tách khỏi validation per-field (design-note D11 §2).

    Cạnh nối về `n2`, không phải `n1`: nối về `n1` (node duy nhất không có incoming edge) sẽ
    khép TOÀN BỘ đồ thị thành 1 vòng kín — 0 start-node candidate — và khi đó luật 3 (kit#87,
    D12: đúng 1 start node) sẽ bắt trước, che mất chính luật 2 mà test này nhắm tới.
    """
    payload = _payload()
    payload["dag"]["edges"].append({"from": "n4", "to": "n2", "when": None})

    with pytest.raises(ValueError, match="cycle"):
        recipe_from_canvas(payload)


def test_rule_3_dangling_edge_is_rejected() -> None:
    """KHÓA luật 3: cạnh trỏ tới node không tồn tại bị chặn, không bị âm thầm bỏ qua."""
    payload = _payload()
    payload["dag"]["edges"][-1]["to"] = "node-khong-ton-tai"

    with pytest.raises(ValueError, match="destination"):
        recipe_from_canvas(payload)


def test_rule_4_tool_outside_whitelist_is_rejected() -> None:
    """KHÓA luật 4: node `tool-call` gọi tool ngoài `agent_config.tool_whitelist` bị chặn.

    Đây là case Inspector của canvas cố ý cho người dùng dựng được (dropdown có sẵn 1 lựa chọn
    ngoài whitelist) — để cổng fail-closed là thứ demo được, không phải thứ chỉ tồn tại trong test.

    Fixture happy-path (từ `sampleGraph()`, kit#206 ADR-D24-01) không còn tự sinh node `tool-call`
    nào — chèn tường minh 1 node vào giữa `n2 -> n4` cho riêng test này, giữ DAG hợp lệ về hình
    dạng (đúng 1 start node, single-successor chain kết ở `end`) trước khi phá whitelist.
    """
    payload = _payload()
    payload["dag"]["nodes"].append({"id": "n3", "type": "tool-call", "params": {"tool": "tool_ngoai_whitelist"}})
    edges = payload["dag"]["edges"]
    edges[:] = [edge for edge in edges if not (edge["from"] == "n2" and edge["to"] == "n4")]
    edges.append({"from": "n2", "to": "n3", "when": None})
    edges.append({"from": "n3", "to": "n4", "when": None})

    with pytest.raises(ValueError, match="whitelist"):
        recipe_from_canvas(payload)


# ---------------------------------------------------------------------------
# Hồi quy — hình dạng form D4 cũ không được sống lại
# ---------------------------------------------------------------------------


def test_legacy_form_shape_is_rejected() -> None:
    """KHÓA: hình dạng mà form D4 cũ xuất ra (`tenant` slug, không `golden_set_ref`, không
    `scorecard_threshold`) PHẢI bị từ chối.

    Không phải test cho code mới — là bẫy chống hồi quy cho đúng lỗi D12 sửa. Contract đổi
    `tenant` → `tenant_id: UUID` từ D-13 và `App.tsx` không đi theo; vì UI chưa bao giờ gọi
    xuống Python nên không có gì phát hiện. Test này đứng ở khe đó từ nay.
    """
    payload = _payload()
    payload["tenant"] = "ankor"
    del payload["tenant_id"]
    del payload["golden_set_ref"]
    del payload["scorecard_threshold"]

    with pytest.raises(ValueError):
        recipe_from_canvas(payload)


def test_seam_never_returns_an_unlinted_recipe() -> None:
    """KHÓA: `recipe_from_canvas` không có nhánh nào trả recipe chưa qua lint.

    Payload dưới đây hợp lệ 100% về kiểu — `Recipe.model_validate()` cho qua sạch — nhưng có
    chu trình. Nếu khe này chỉ validate mà quên gọi `graph_lint`, hàm sẽ trả về recipe bình
    thường và test đỏ. Đó là điều kiện "fail-closed" của DoD ô 2, khoá ở tầng API chứ không chỉ
    ở tầng luật.
    """
    payload = _payload()
    payload["dag"]["edges"] = [
        {"from": "n1", "to": "n2", "when": None},
        {"from": "n2", "to": "n1", "when": None},
    ]

    with pytest.raises(ValueError):
        recipe_from_canvas(payload)
