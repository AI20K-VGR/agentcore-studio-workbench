"""Khe nối canvas → contract → cổng agent-shape/agent-topology lint (D12, kit#87; app#44 rewrite)
— bút SWE.

`apps/web` cho người dùng kéo-thả node thành DAG rồi xuất ra recipe JSON. Module này là chỗ DUY
NHẤT recipe đó được phép đi vào phía Python: nó parse qua `studio_contracts.Recipe` rồi chạy
`enforce_agent_shape()` + `enforce_agent_topology()` — không có đường nào lấy được `Recipe` từ
canvas mà chưa qua cả 2 lint.

**app#44:** `graph_lint()` (DAG-topology, 7 luật cũ) bị XOÁ — thay bằng `agent_topology_lint`
(hình sao mới: 1 llm-step tâm, 0-1 kb-retrieve + N tool-call làm cánh, xem `validator.py` module
docstring) + `agent_shape_lint` (agent_config/kb_binding/golden_set_ref, không đọc `dag`).

## Vì sao là module riêng, không nhét vào `recipe.py`
`recipe.py` chứa hàm DỰNG recipe từ tham số đã có kiểu (`create_recipe`, workbench#41 — `create_recipe_d4`
đã bị xoá) — đầu vào
của nó đã là `Node`/`Edge` hợp lệ, và nó cố ý KHÔNG lint (dựng và kiểm là 2 việc khác nhau).
Khe canvas thì ngược lại: đầu vào là JSON tự do từ trình duyệt, chưa có gì bảo đảm, và bắt buộc
phải lint. Trộn 2 nhóm vào 1 file sẽ khiến người đọc phải nhớ "hàm nào lint, hàm nào không" —
tách ra thì tên module tự trả lời.

## Fail-closed
Hàm hoặc trả về 1 `Recipe` đã qua lint, hoặc raise. Không có nhánh nào trả về recipe kèm cờ
"chưa lint" để người gọi tự quyết — đó chính là kiểu API mà design-note D11 §6 đã bỏ (người gọi
quên kiểm thì recipe hỏng lọt qua như thể hợp lệ).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from studio_contracts import Recipe

from studio_workbench.validator import enforce_agent_shape, enforce_agent_topology


def recipe_from_canvas(payload: Mapping[str, Any]) -> Recipe:
    """Nhận recipe JSON do canvas xuất ra, trả về `Recipe` ĐÃ qua cả `enforce_agent_shape` VÀ
    `enforce_agent_topology`.

    Args:
        payload: dict đã `json.loads` từ output của canvas (`apps/web`), theo đúng hình dạng dây
            của `studio_contracts.Recipe` — `dag.edges[].from` dùng alias `from` (F12).

    Returns:
        `Recipe` hợp lệ cả về kiểu (Pydantic), shape `agent_config`/`kb_binding`/`golden_set_ref`
        (`agent_shape_lint`), lẫn cấu trúc đồ thị hình sao (`agent_topology_lint`).

    Raises:
        ValueError: payload sai hình dạng contract, HOẶC vi phạm 1 luật `agent_shape_lint`/
            `agent_topology_lint`. Cả 3 nguồn đều là `ValueError`:
            `pydantic.ValidationError` kế thừa `ValueError`, nên chỗ gọi bắt được cả 3 bằng 1
            `except ValueError` mà không cần biết lỗi rơi ở tầng nào. Không nuốt lỗi và không đổi
            kiểu ngoại lệ — thông điệp gốc chỉ đúng chỗ sai là thứ UI cần để tô đỏ đúng chỗ.
    """
    recipe = Recipe.model_validate(payload)
    enforce_agent_shape(recipe)
    enforce_agent_topology(recipe)
    return recipe


__all__ = ["recipe_from_canvas"]
