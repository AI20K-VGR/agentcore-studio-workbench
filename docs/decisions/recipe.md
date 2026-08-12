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

## D18 · 2026-08-12 — kit#117, `publish()`/`rollback()` thân hàm thật

| # | Quyết định | Lý do | PR / bằng chứng | Trạng thái |
|---|---|---|---|---|
| DL-R4 | Q5 (`docs/test-design/GUIDE-B-recipe.md` §10) — `publish`/`rollback` nhận `conn: DbConnection` (Protocol mới, đặt trong `studio_workbench/protocols.py`, **không** đưa lên `studio_contracts`) thay vì tự mở connection hoặc nhận cả pool | `studio_workbench` không import được `studio_app` (`.importlinter`); nhận đúng 1 connection đã bind sẵn tenant khiến việc tự mở connection không-bind là bất khả thi về mặt cấu trúc (B-P01). Không đưa Protocol lên `studio_contracts`: chỉ 1 consumer (`publish()`/`rollback()`) + 1 producer (`apps/studio`, đã được phép import `studio_workbench`) — cùng lý do AIE-2 đã tự rút lại việc promote `AgentRunner` ([`MRFC-2026-08-03-agentrunner-protocol-seam.md`](https://github.com/AI20K-VGR/agentcore-studio-evalhub/blob/main/docs/mini-rfc/MRFC-2026-08-03-agentrunner-protocol-seam.md) §4) — nên **không cần mini-RFC** | `packages/workbench` branch `swe/day18-publish-rollback` | 🟡 chờ review |
| DL-R5 | Q7 — bật RLS (`ENABLE`+`FORCE ROW LEVEL SECURITY` + policy) cho `wb.recipes`/`wb.recipe_versions`, mẫu `kb_chunks_tenant_isolation` | 2 bảng chứa IP tenant (`agent_config.instructions`, `kb_binding.scope`) với đường ghi/đọc thật lần đầu qua `publish()`/`rollback()` | Ký phần B ở [`packages/kb/docs/mini-rfc-tenant-schema-unify.md`](https://github.com/AI20K-VGR/agentcore-studio-kb/blob/main/docs/mini-rfc-tenant-schema-unify.md) (2026-08-12) + implement cùng branch trên | 🟡 chờ review |
| DL-R6 | `Scorecard.recipe_hash is None` → `publish()` fail-closed (refuse), không tự nới lỏng | Đúng docstring `recipe_hash` (`scorecard.py:216-220`): "cannot verify which recipe this certifies ⇒ REFUSE". Every real `Scorecard` mang `None` tới khi AIE-2 wire producer (`DEC-03`) — `publish()` sẽ luôn refuse tới lúc đó, đây là hành vi đúng, không phải bug | `packages/workbench` branch `swe/day18-publish-rollback` | 🟢 implement xong |

## Còn mở — chặn `FROZEN` thật sự

| # | Nội dung | Chờ ai |
|---|---|---|
| Q-1 | Cơ chế "freeze" (lật cờ tự do vs cần PR vào `contracts`) — đề xuất ở ADR-D11-01, chưa có đồng thuận | cả nhóm (hạn: hết ngày 03/08) |
| — | PR [workbench#12](https://github.com/AI20K-VGR/agentcore-studio-workbench/pull/12) chưa được review/merge | DE, AIE-1, AIE-2 |
| Q-Publish | `publish(recipe, scorecard)` cần `Scorecard` thật (không phải `SmokeResult`) — thân hàm đã nhận đúng `Scorecard` thật từ D18, nhưng pipeline sinh `Scorecard` thật (judge branch) của AIE-2 chưa xong | AIE-2 |
| Q4 (register §10) | "Đúng 1 live version" cho `(agent_id, tenant_id)` chưa được enforce ở tầng DB (partial unique index / advisory lock) — D18 chỉ enforce ở tầng application, best-effort | SWE, chưa có ETA |

**Chưa lật `freeze: FROZEN`** — điều kiện trên chưa đủ.
