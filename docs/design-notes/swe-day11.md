---
id: studio.design-note.swe.day-11
type: design-note
role: SWE — Thiệu Quang Minh
day: 11
date: 2026-08-03
status: draft (chờ mentor duyệt — DoD #82 ô 2)
scope: canvas 6-node · recipe validator/graph-lint · 1 phương án bỏ
length_target: ≤2 trang
---

# Design-note SWE (D11) — Recipe schema: canvas 6-node → validator/graph-lint → publish gate

> Neo: issue **#82** (*"Bút recipe schema... Design-note: canvas 6-node + validator/graph-lint +
> 1 phương án bỏ"*). Không tóm tắt contract — đây là **thiết kế + đánh đổi**. Hợp đồng đã khoá hôm nay
> ([`recipe.v0.md`](../contracts/recipe.v0.md)) là *hình dạng dây*; note này là *vì sao Workbench phía
> sau contract lại có hình đó*.

## 1. Bài toán một câu

Workbench phải để người dùng **khai báo** 1 agent (không viết code) mà kết quả khai báo đó vẫn
**đúng-do-cấu-trúc** — không cho phép tạo ra 1 recipe mà interpreter (AIE-1) đọc vào sẽ vỡ hoặc chạy
sai luật. `graph_lint()` là cổng duy nhất đứng giữa "người dùng khai báo" và "engine thực thi".

## 2. Vì sao validator tách khỏi Pydantic construct-time validation

Pydantic (`Node.type: NodeType`) đã chặn được **1 trong 4 luật** (node type ∈ 6 đóng) ngay lúc dựng
object. Nhưng 3 luật còn lại — không chu trình, edge có đích, tool ∈ whitelist — là **ràng buộc giữa
nhiều field/nhiều node với nhau**, Pydantic per-field validation không biểu diễn được. Đây là lý do
`graph_lint()` tồn tại như 1 hàm riêng thay vì cố nhét hết vào `model_validator` của `Recipe`:
tách sự-thật-cấu-trúc-đơn-lẻ (Pydantic) khỏi sự-thật-về-mối-quan-hệ (`graph_lint`), 2 tầng lỗi khác
nhau nên 2 cơ chế bắt lỗi khác nhau.

## 3. Thứ tự 4 luật — không tuỳ ý, tránh 1 lớp phải đoán lớp trước

`node-type → edge-destination → cycle → tool-whitelist`. Điểm cố ý: **edge-destination đứng trước
cycle**. Nếu đảo ngược, vòng DFS phát hiện cycle sẽ gặp `edge.to` trỏ tới 1 node không tồn tại (case
"dangling edge") và phải tự quyết định coi đó là lỗi gì — trộn 2 loại lỗi khác nhau vào 1 thông báo.
Kiểm tra đích-tồn-tại trước khi đi bộ đồ thị nghĩa là lúc DFS chạy, mọi cạnh chắc chắn trỏ tới node
có thật — DFS chỉ còn đúng 1 việc để lo (cycle), không phải vừa lo cycle vừa lo dữ liệu vào có sạch
không.

## 4. `graph_lint` raise `ValueError`, không trả `bool`/list lỗi

Quyết định: hàm hoặc thành công im lặng (`None`), hoặc raise ở vi phạm ĐẦU TIÊN tìm thấy — không
gom hết lỗi trả về 1 danh sách. Đánh đổi: người dùng Workbench UI sửa lỗi phải sửa-rồi-thử-lại nhiều
lần thay vì thấy hết lỗi 1 lượt (UX kém hơn). Chọn vậy vì `graph_lint` là **cổng chặn trước
interpreter** (R-SPEC A1#1: *"recipe không qua validator = không interpret"*), không phải bộ linter
tương tác — dừng cứng ở vi phạm đầu tiên đơn giản hơn, và tránh trường hợp danh sách lỗi dài làm
người raise nhầm tưởng "sửa hết danh sách là chắc chắn qua", trong khi thứ tự sửa có thể sinh ra vi
phạm mới không nằm trong danh sách ban đầu (vd sửa cycle xong lại lộ ra dangling edge bị cycle che
trước đó).

## 5. `publish()`/`rollback()` — ranh giới với `Scorecard` của AIE-2

`publish(recipe, scorecard)` (`src/studio_workbench/publish.py`, còn stub) chỉ **đọc**
`scorecard.gate.verdict`, không tự tính lại verdict — SWE wire cổng, không sở hữu việc render
scorecard. Ranh giới này giữ nguyên dù `Scorecard` hiện chưa sinh ra được từ dữ liệu thật (AIE-2 đang
vướng field `judge` bắt buộc, xem PR [contracts#1](https://github.com/AI20K-VGR/agentcore-studio-contracts/pull/1)) —
SWE không tự tính verdict thay AIE-2 dù đang thiếu input để test end-to-end, vì làm vậy tái tạo đúng
kiểu chồng lấn ownership mà ranh giới quadrant (umbrella §2) tồn tại để ngăn.

## 6. Một phương án đã BỎ — validator trả `list[str]` (gom hết lỗi)

**Phương án:** `graph_lint(recipe) -> list[str]` — chạy hết 4 luật, gom mọi vi phạm vào 1 danh sách,
rỗng nghĩa là hợp lệ. **Bỏ vì:** (1) đổi API thành "trả giá trị rồi người gọi tự kiểm tra rỗng hay
không" — dễ quên kiểm tra (`if errors:` bị bỏ sót thì recipe lỗi lọt qua như thể hợp lệ), trong khi
raise thì không thể "quên" theo cách đó; (2) như đã nói ở §4, danh sách lỗi tĩnh tại 1 thời điểm có
thể sai lệch sau khi sửa 1 lỗi (lỗi này che lỗi khác); (3) `test_lint_rejects_bad_graph` (đã tồn tại
từ D-spec) neo theo `pytest.raises(ValueError, match=...)` — đổi sang trả list là breaking test-spec
đã có, không phải chỉ đổi implementation nội bộ.

## 7. Điểm S2/S3 đã biết (nêu trước, không giấu)

- `kb_binding.scope` hiện chưa được `interpreter` đọc để suy tenant/section_roles — fence chunk-level
  thật (S3) sẽ cần chốt lại: `kb_binding` chỉ mô tả *khai báo*, hay bắt đầu ảnh hưởng *hành vi
  runtime* thật. Ghi trong [`recipe.v0.md` §3](../contracts/recipe.v0.md).
- Canvas kéo-thả (React Flow) chưa triển khai — hiện Workbench build recipe qua `builder.py`
  (form-driven), đúng Nấc 2 của `DESCOPE.md`. `graph_lint` không phụ thuộc UI nào — validator hoạt
  động y hệt dù input tới từ canvas hay form.
