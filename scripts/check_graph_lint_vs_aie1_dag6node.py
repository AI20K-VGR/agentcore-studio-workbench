"""GATE-2 (Day 20, kit#127 mục "6 node-type") — xác nhận `graph_lint()` (workbench) chấp nhận
đúng DAG 6-node mẫu của AIE-1 (`engine#25`, `packages/engine/scripts/run_spine_dag_6node.py`).

Đứng NGOÀI `src/studio_workbench/` cố ý, cùng lý do `dev_playground_server.py`/
`apps/studio/scripts/e2e_smoke_eval.py` đã làm: script cần import CẢ `studio_workbench`
(`graph_lint`) LẪN đọc file thuộc `studio_engine`'s `scripts/` (không phải qua `studio_engine`
package — `build_six_node_recipe` không export qua `__init__.py`, chỉ tồn tại trong 1 file script)
— `.importlinter`'s layers contract chỉ soi import graph BÊN TRONG mỗi root package, một script
rời không thuộc package nào thì không lọt vào graph đó.

Chạy: uv run python packages/workbench/scripts/check_graph_lint_vs_aie1_dag6node.py
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path

from studio_contracts import Recipe

from studio_workbench.validator import graph_lint

_ENGINE_SCRIPT = (
    Path(__file__).resolve().parents[2] / "engine" / "scripts" / "run_spine_dag_6node.py"
)


def _load_build_six_node_recipe() -> Callable[[], Recipe]:
    spec = importlib.util.spec_from_file_location("run_spine_dag_6node", _ENGINE_SCRIPT)
    assert spec is not None and spec.loader is not None, f"không nạp được {_ENGINE_SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_spine_dag_6node"] = module
    spec.loader.exec_module(module)
    build: Callable[[], Recipe] = module.build_six_node_recipe
    return build


def main() -> None:
    build_six_node_recipe = _load_build_six_node_recipe()
    recipe = build_six_node_recipe()
    try:
        graph_lint(recipe)
    except ValueError as exc:
        raise SystemExit(
            f"FAIL: graph_lint() TỪ CHỐI DAG 6-node của AIE-1 — {exc}\n"
            "Cần báo lại AIE-1 (PR#25 xin review shape-compatibility) để thống nhất sửa bên nào."
        ) from exc
    print(
        "OK: graph_lint() (workbench) chấp nhận đúng DAG 6-node mẫu của AIE-1 "
        f"(engine#25, agent_id={recipe.agent_id!r}, {len(recipe.dag.nodes)} node, "
        f"{len(recipe.dag.edges)} edge) — không cần sửa bên nào cho tương thích shape."
    )


if __name__ == "__main__":
    main()
