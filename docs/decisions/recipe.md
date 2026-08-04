---
id: studio.decision-log.recipe
type: decision-log
contract: recipe
pen: SWE — Thiệu Quang Minh
freeze: FREEZE-READY   # chưa FROZEN — xem điều kiện còn thiếu bên dưới
---

# Decision-log — recipe (SWE)

## D11 · 2026-08-03

| # | Quyết định | Lý do | PR / bằng chứng | Trạng thái |
|---|---|---|---|---|
| DL-R1 | `graph_lint()` implement thân hàm thật, 4 luật (node-type ∈ 6 đóng, edge-destination resolvable, no cycle, tool ∈ whitelist), thứ tự kiểm: node-type → edge-destination → cycle → tool-whitelist | Trước là spec-stub `NotImplementedError`; thứ tự cố ý để DFS tìm cycle không phải đoán xử lý dangling edge | [workbench#12](https://github.com/AI20K-VGR/agentcore-studio-workbench/pull/12) | 🟡 chờ review |
| DL-R2 | Q-4 (recipe.dag's node_type = đúng 6 `NodeType`, DE hỏi ở kb#10) — đóng | `recipe.py` và `trace.py` dùng chung `studio_contracts.nodes.NodeType`; Pydantic chặn ở tầng kiểu | [kb#10 comment](https://github.com/AI20K-VGR/agentcore-studio-kb/pull/10#issuecomment-5162808694) | ✅ đóng |
| DL-R3 | Shape `Recipe` (agent_id/tenant_id/agent_config/dag/kb_binding/golden_set_ref/scorecard_threshold) — không đổi field/kiểu nào hôm nay | Đã khớp `studio_contracts.recipe.Recipe` từ D-13, xác nhận qua `builder.py` D3/D4/D6 + `test_recipe_roundtrip.py` | [`recipe.v0.md`](https://github.com/AI20K-VGR/agentcore-studio-workbench/blob/day11/recipe-freeze-ready/docs/contracts/recipe.v0.md) (PR #12, chưa merge `main`) | ✅ đóng |

## Còn mở — chặn `FROZEN` thật sự

| # | Nội dung | Chờ ai |
|---|---|---|
| Q-1 | Cơ chế "freeze" (lật cờ tự do vs cần PR vào `contracts`) — đề xuất ở ADR-D11-01, chưa có đồng thuận | cả nhóm (hạn: hết ngày 03/08) |
| — | PR [workbench#12](https://github.com/AI20K-VGR/agentcore-studio-workbench/pull/12) chưa được review/merge | DE, AIE-1, AIE-2 |
| Q-Publish | `publish(recipe, scorecard)` cần `Scorecard` thật (không phải `SmokeResult`) — chưa có | AIE-2 |

**Chưa lật `freeze: FROZEN`** — 3 điều kiện trên chưa đủ cả 3.
