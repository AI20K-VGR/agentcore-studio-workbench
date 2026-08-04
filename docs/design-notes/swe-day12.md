---
id: studio.design-note.swe.day-12
type: design-note
role: SWE — Thiệu Quang Minh
day: 12
date: 2026-08-04
status: draft (chờ mentor duyệt — DoD #87)
scope: canvas React Flow 6-node · khe canvas→contract→graph-lint · Mermaid nấc 2
supersedes: swe-day11.md §7 (mục "Canvas kéo-thả (React Flow) chưa triển khai" — nay đã có)
length_target: ≤2 trang
---

# Design-note SWE (D12) — Canvas 6-node: từ "form xuất DAG hardcode" sang "recipe do canvas sinh"

> Neo: issue **[kit#87](https://github.com/AI20K-VGR/agentcore-studio-kit/issues/87)**. Note D11 tả
> *vì sao `graph_lint()` có hình đó*; note này tả *vì sao thứ đứng TRƯỚC nó — canvas — có hình đó*,
> và một lỗi hợp đồng phát hiện được đúng lúc nối 2 đầu lại.

## 1. Việc thật của D12 hoá ra không phải "vẽ UI"

`graph_lint()` đã xong từ D11. Nên D12 nghe như chỉ còn phần nhìn. Nhưng khi nối canvas vào
contract thì lộ ra: **recipe mà Workbench UI đang xuất chưa từng đi lọt qua `Recipe` lần nào.**

`apps/web/src/App.tsx` bản D4 xuất ra:

| Field | Bản D4 xuất | Contract đòi |
|---|---|---|
| tenant | `"tenant": "ankor"` (slug) | `tenant_id: UUID` — đổi từ **D-13** |
| `golden_set_ref` | *không có* | bắt buộc |
| `scorecard_threshold` | *không có* | bắt buộc |

`Recipe.model_validate()` sẽ từ chối payload đó ngay ở field đầu. Lỗi này sống sót được vì UI chưa
bao giờ gọi xuống Python — nó `JSON.stringify` ra `<pre>` cho người xem, và không có gì ở giữa để
phản đối. Cùng lý do khiến `dag` trong bản đó là **4 node hardcode** không liên quan gì tới canvas
rỗng bên cạnh: không ai tiêu thụ nó nên không ai phát hiện.

Bài học ghi lại: *một cái seam không có ai đi qua thì không phải seam, nó là 2 cái ống không nối.*
Việc D12 vì vậy gồm cả dựng canvas lẫn **đóng khe đó bằng test** — `test_legacy_form_shape_is_rejected`
(`test_wiring_d12.py`) dựng lại đúng hình dạng D4 và bắt nó phải bị từ chối, để lỗi này không quay lại.

## 2. `recipe_from_canvas()` — vì sao là module riêng, không phải hàm thứ 5 trong `builder.py`

`builder.py` chứa các hàm **dựng** recipe từ tham số đã có kiểu (`create_recipe_d3/d4/d6`); đầu vào
của chúng đã là `Node`/`Edge` hợp lệ và chúng **cố ý không lint** — dựng và kiểm là 2 việc khác nhau.
Khe canvas ngược lại: đầu vào là JSON tự do từ trình duyệt, và **bắt buộc** phải lint.

Trộn 2 nhóm vào 1 file buộc người đọc phải nhớ "hàm nào lint, hàm nào không" — một luật ngầm nằm
trong đầu người chứ không nằm trong code. Tách ra `canvas.py` thì tên module tự trả lời, và chữ ký
hàm không có nhánh nào trả về recipe kèm cờ "chưa lint" để người gọi tự quyết — đúng loại API mà
note D11 §6 đã bỏ.

## 3. Bản lint TS là GƯƠNG, không phải cổng thứ hai

Canvas cần báo lỗi ngay khi người dùng nối sai, không thể đợi round-trip xuống server. Nên 4 luật
được chép sang `src/recipe/graphLint.ts`. Ranh giới phải nói rõ, vì nhầm chỗ này là nhầm về an ninh:

- Cổng thật vẫn **chỉ** là `graph_lint()` Python. Client báo "sạch" **không** cho phép bỏ qua nó.
- Client báo "hỏng" thì UI **chặn export luôn** (nút `disabled`, tab JSON dán nhãn *CHƯA QUA LINT*).
- Lệch nhau thì luôn nghiêng về phía **chặn** — gương chặt hơn cổng thì chỉ phiền, gương lỏng hơn
  cổng thì recipe hỏng đi tiếp một quãng rồi mới chết, xa chỗ người dùng gây ra nó.

Hệ quả của luật trên: **cấm thêm luật thứ 5 vào bản mirror.** Những thứ đáng nhắc mà `graph_lint()`
không chặn (canvas trống, thiếu node `end`, node mồ côi, tool bật mà không ai gọi) đi qua hàm
`advisories()` riêng, hiện màu vàng, **không** khoá export. Nhét chúng vào `graphLint()` sẽ khiến
canvas từ chối những recipe mà hệ thống thật vẫn nhận — lúc đó nó hết là gương.

## 4. Drift giữa 2 bản: rủi ro biết trước, và giá phải trả để giữ

Viết 4 luật 2 lần bằng 2 ngôn ngữ **sẽ** lệch nếu không có gì giữ. Hai thứ giữ nó:

1. **`pnpm emit-fixture`** — `tests/fixtures/canvas_export_d12.json` được **sinh từ chính**
   `buildRecipe()` + `sampleGraph()` mà canvas dùng, không gõ tay. Fixture gõ tay sẽ đứng yên khi
   canvas đổi hình dạng, và test vẫn xanh trong khi khe đã gãy — tức là test khẳng định một điều
   không còn đúng. Sinh từ code thì canvas đổi mà quên chạy lại sẽ lộ ở diff.
2. **`pnpm check-parity`** — chạy đúng 5 case của `test_wiring_d12.py` (1 happy + 4 luật) qua bản
   TS và đối chiếu phán quyết. Điểm cần nói thẳng: `test_wiring_d12.py` khoá được *hình dạng output
   của canvas* nhưng **không** khoá được *bản TS có phán quyết giống bản Python* — nó không chạy code
   TS. Parity script đứng đúng vào khoảng trống đó.

Cái giá đã cân: phương án "không chép luật, canvas gọi API `/lint` của server" thì **không có** drift,
nhưng đổi lại mỗi thao tác nối cạnh phải đi 1 vòng mạng, và canvas thành vô dụng khi backend chưa
chạy — trong khi S1/S2 vẫn còn đang dựng backend. Chép + 2 thứ giữ ở trên là đánh đổi chọn có ý thức,
không phải quên.

## 5. Một phương án đã BỎ — sinh `Node.id` theo thứ tự tôpô lúc export

**Phương án:** khi export, đánh số lại node theo thứ tự thực thi (`n1` là gốc, tăng dần theo chiều
cạnh) cho recipe đọc đẹp. **Bỏ vì:** id lúc đó thành **hàm của hình dạng đồ thị** — người dùng nối
thêm 1 cạnh ở giữa là toàn bộ id phía sau đổi theo. Mọi thứ trỏ tới node bằng id (trace event
`node_id`, thông điệp lỗi của graph-lint, `wb.recipe_versions` bản trước) lập tức trỏ sai chỗ mà
không có gì báo. Id do canvas cấp lúc **tạo** node và không bao giờ đổi nữa thì xấu hơn nhưng ổn định
— và ổn định là thứ trace cần.

## 6. Mermaid: nấc 2 dựng sẵn, **chưa** kích hoạt — nên không có decision-log

`DESCOPE.md` Nấc 2 là *"Canvas React Flow → Form + Mermaid"*, kích hoạt khi SWE chưa làm kịp canvas.
Canvas **đã làm kịp**. Tab Mermaid vẫn có mặt, nhưng nó là **cách nhìn song song** của cùng
`recipe.dag` (cùng nguồn với canvas và với export, không phải nhánh dữ liệu thứ hai), không phải
fallback đang chạy thay.

Vì vậy DoD ô 4 (*"nếu tụt nấc → decision-log ghi"*) **không áp dụng** hôm nay, và cố ý không ghi
decision-log tụt nấc. Ghi một lần tụt nấc không xảy ra là làm bẩn đúng cái sổ mà cả nhóm dựa vào để
biết hệ thống đang ở nấc nào.

## 7. Điểm còn mở / chưa làm (nêu trước, không giấu)

- **Canvas chưa gọi xuống Python.** `recipe_from_canvas()` đã sẵn ở phía server, nhưng nút export
  hiện chỉ đưa JSON ra màn hình cho người dùng copy; chưa có HTTP endpoint nối 2 đầu. Đây là lý do
  parity script tồn tại — chừng nào chưa nối thật, nó là thứ duy nhất bắt được drift.
- **`apps/web` chưa có test runner** (không vitest/jest). Parity script viết bằng assertion trần +
  `process.exit`, chạy qua `scripts/run.mjs`. Kéo cả 1 runner về chỉ cho 5 assertion là quyết định
  riêng, không nhét kèm vào issue canvas.
- **`publish()` vẫn stub** — chờ Q-Publish với AIE-2 (`Scorecard` thật). Không tự tính verdict thay,
  giữ nguyên ranh giới note D11 §5.
- **`kb_binding.scope`** vẫn chỉ là khai báo, chưa quyết fence runtime — việc S3, `recipe.v0.md` §3.

## 8. Kiểm chứng

| Lệnh | Kết quả |
|---|---|
| `uv run pytest packages/workbench` | 77 passed, 1 skipped (8 test D12 mới) |
| `uv run ruff check .` · `mypy packages apps` · `lint-imports` | sạch cả 3 |
| `pnpm build` (`tsc --noEmit && vite build`) | xanh |
| `pnpm check-parity` | 5/5 case khớp `test_wiring_d12.py` |

Contract **không đổi** field/kiểu nào ở D12 — `recipe.v0.md` giữ nguyên, không cần mini-RFC.
