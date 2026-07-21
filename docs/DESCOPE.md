# 🪜 DANH SÁCH CẮT GIẢM TÍNH NĂNG CHUẨN (DESCOPE-LADDER)

> **Nguyên tắc cốt lõi (INV-7):** Cắt độ bóng, không cắt nhịp demo. Khi gặp rào cản kỹ thuật hoặc trễ tiến độ, hệ thống sẽ tự động hạ cấp tính năng theo 4 nấc dưới đây. Mỗi nấc hạ cấp **BẮT BUỘC** phải đảm bảo luồng **Walking-Skeleton (8 bước từ A-Z) VẪN SỐNG**.

---

## 📐 BẢNG 4 NẤC CẮT GIẢM (DESCOPE LADDER)

| Nấc | Thành phần | Trạng thái gốc (Target) | Nấc cắt giảm (Fallback) | Điều kiện kích hoạt Fallback |
| :--- | :--- | :--- | :--- | :--- |
| **Nấc 1** | **KB Pipeline** | Vector Search + RAG Pipeline thực tế | **Stub Tĩnh (5 Docs)** | Khi Pipeline KB / Embedding Service bị kẹt hoặc lỗi kết nối. |
| **Nấc 2** | **Workbench UI** | Canvas Kéo-Thả (React Flow) | **Form Nhập Liệu + Mermaid Diagram** | Khi SWE chưa làm kịp React Flow UI / Canvas bị lỗi rendering. |
| **Nấc 3** | **Eval Scorer** | LLM-Judge tự động chấm điểm | **Exact-match Scorer** | Khi LLM Judge hết quota ($\le 100$ calls/ngày) hoặc nondeterministic. |
| **Nấc 4** | **Dashboard** | Web UI Dashboard giám sát | **CLI Table Output** | Khi Web UI Dashboard chưa hoàn thiện. |

---

## 🔍 CHI TIẾT TỪNG NẤC

### 1. Nấc 1: Knowledge Base (KB) ➔ Stub Tĩnh
- **Mô tả:** Nếu hệ thống Vector DB hoặc RAG Pipeline chưa hoàn thành ở Sprint 1, `kb.search` sẽ trả về danh sách 5 tài liệu tĩnh (fixtures) được định nghĩa trước.
- **Bảo toàn Walking-Skeleton:** Node `kb-retrieve` vẫn nhận query và trả về context hợp lệ để `llm-step` tiêu thụ.

### 2. Nấc 2: Canvas Visual UI ➔ Form + Mermaid
- **Mô tả:** Thay vì kéo thả đồ thị các node trên Canvas bằng React Flow, người dùng nhập cấu hình qua Form nhập liệu chuẩn. Hệ thống tự động biên dịch DAG JSON sang chuỗi sơ đồ **Mermaid** để preview visual graph.
- **Bảo toàn Walking-Skeleton:** Dữ liệu Recipe JSON sinh ra từ Form hoàn toàn đúng định dạng spec v0 và đi qua `graph_lint` bình thường.

### 3. Nấc 3: LLM Judge ➔ Exact-match Scorer
- **Mô tả:** Khi gặp giới hạn Quota API hoặc cần chấm điểm nhanh, bộ kiểm định EvalHub chuyển từ LLM-Judge sang bộ so sánh chuỗi exact-match / keyword match.
- **Bảo toàn Walking-Skeleton:** Scorecard vẫn xuất ra kết quả `PASS/FAIL` cùng các chỉ số cơ bản để `publish` đưa ra quyết định.

### 4. Nấc 4: Dashboard ➔ CLI Output
- **Mô tả:** Khi Web Dashboard chưa sẵn sàng, các dữ liệu về execution trace, cost breakdown và log được định dạng dưới dạng bảng Markdown / ASCII và in trực tiếp ra CLI terminal.
- **Bảo toàn Walking-Skeleton:** Người vận hành vẫn quan sát được toàn bộ trace và cost lineage 3 surface mà không làm tắc nghẽn luồng.
