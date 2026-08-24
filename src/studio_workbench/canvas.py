"""Khe nối canvas → contract → cổng graph-lint (D12, issue kit#87) — bút SWE.

`apps/web` cho người dùng kéo-thả 6 loại node thành DAG rồi xuất ra recipe JSON. Module này là
chỗ DUY NHẤT recipe đó được phép đi vào phía Python: nó parse qua `studio_contracts.Recipe` rồi
chạy `graph_lint()` — không có đường nào lấy được `Recipe` từ canvas mà chưa qua lint.

## Vì sao là module riêng, không nhét vào `recipe.py`
`recipe.py` chứa hàm DỰNG recipe từ tham số đã có kiểu (`create_recipe`, workbench#41 — `create_recipe_d4`
đã bị xoá) — đầu vào
của nó đã là `Node`/`Edge` hợp lệ, và nó cố ý KHÔNG lint (dựng và kiểm là 2 việc khác nhau).
Khe canvas thì ngược lại: đầu vào là JSON tự do từ trình duyệt, chưa có gì bảo đảm, và bắt buộc
phải lint. Trộn 2 nhóm vào 1 file sẽ khiến người đọc phải nhớ "hàm nào lint, hàm nào không" —
tách ra thì tên module tự trả lời.

## Fail-closed
Hàm hoặc trả về 1 `Recipe` đã qua đủ 4 luật, hoặc raise. Không có nhánh nào trả về recipe kèm cờ
"chưa lint" để người gọi tự quyết — đó chính là kiểu API mà design-note D11 §6 đã bỏ (người gọi
quên kiểm thì recipe hỏng lọt qua như thể hợp lệ).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from studio_contracts import Recipe

from studio_workbench.validator import graph_lint


def recipe_from_canvas(payload: Mapping[str, Any]) -> Recipe:
    """Nhận recipe JSON do canvas xuất ra, trả về `Recipe` ĐÃ qua `graph_lint`.

    Args:
        payload: dict đã `json.loads` từ output của canvas (`apps/web`), theo đúng hình dạng dây
            của `studio_contracts.Recipe` — `dag.edges[].from` dùng alias `from` (F12).

    Returns:
        `Recipe` hợp lệ cả về kiểu (Pydantic) lẫn về cấu trúc đồ thị (4 luật graph-lint).

    Raises:
        ValueError: payload sai hình dạng contract, HOẶC vi phạm 1 trong 4 luật graph-lint.
            Cả 2 đều là `ValueError`: `pydantic.ValidationError` kế thừa `ValueError`, nên chỗ
            gọi bắt được cả hai bằng 1 `except ValueError` mà không cần biết lỗi rơi ở tầng nào.
            Không nuốt lỗi và không đổi kiểu ngoại lệ — thông điệp gốc chỉ đúng chỗ sai là thứ
            UI cần để tô đỏ đúng node.
    """
    recipe = Recipe.model_validate(payload)
    graph_lint(recipe)
    return recipe


__all__ = ["recipe_from_canvas"]
