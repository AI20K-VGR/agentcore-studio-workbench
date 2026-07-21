# 📝 PHÁC THẢO CÁC TRƯỜNG DỮ LIỆU FORM WORKBENCH (FORM FIELDS SKETCH)

> Tài liệu phác thảo danh sách các trường dữ liệu trên giao diện Workbench Form tạo / chỉnh sửa Agent Recipe (phù hợp cho cả nấc UI gốc và nấc Fallback Form+Mermaid).

---

## 📋 DANH SÁCH CÁC TRƯỜNG DỮ LIỆU (FORM FIELDS)

### 1. Định danh & Phân quyền (Identity & Scope)
| Tên trường | Kiểu dữ liệu | Kiểu Widget UI | Mô tả & Constraint |
| :--- | :--- | :--- | :--- |
| `agent_id` | `string` | Text Input | Mã định danh duy nhất của Agent (slug, ví dụ: `customer-support-bot`). Bắt buộc. |
| `tenant` | `string` | Dropdown / Readonly | Tenant ID sở hữu Agent (kiểm soát bởi `tenant_wall.py`). Bắt buộc. |
| `version` | `string` | Text Input / Auto | Phiên bản Recipe (ví dụ: `v0.1.0`). |

### 2. Cấu hình AI Agent (`agent_config`)
| Tên trường | Kiểu dữ liệu | Kiểu Widget UI | Mô tả & Constraint |
| :--- | :--- | :--- | :--- |
| `instructions` | `text` | Textarea (Code editor) | System prompt / Câu dặn gốc cho AI Agent. |
| `model` | `string` | Dropdown | Tên mô hình AI được chọn (ví dụ: `gemini-2.5-flash`, `gemini-2.5-pro`). |
| `tool_whitelist` | `list[string]` | Multi-select Checklist | Danh sách Tool Agent được phép gọi (ví dụ: `web_search`, `python_interpreter`, `kb_search`). |

### 3. Tích hợp Kho tri thức (`kb_binding`)
| Tên trường | Kiểu dữ liệu | Kiểu Widget UI | Mô tả & Constraint |
| :--- | :--- | :--- | :--- |
| `kb_id` | `string` | Dropdown | ID kho tri thức gán cho Agent (ví dụ: `kb-tech-docs-v1`). |
| `scope` | `string` | Text Input / Select | Phạm vi truy cập tri thức (`public`, `internal`, `confidential`). |

### 4. Đồ thị luồng thực thi (`dag_config`)
Dữ liệu DAG bao gồm danh sách các Node & Edge:
- **Các Node được phép (Khóa đúng 6 NodeType):**
  1. `kb-retrieve`: Node truy xuất tri thức từ KB.
  2. `llm-step`: Node gọi LLM để xử lý / suy luận.
  3. `condition`: Node rẽ nhánh điều kiện.
  4. `tool-call`: Node thực thi tool trong whitelist.
  5. `hitl-pause`: Node dừng chờ con người phê duyệt (Human-in-the-loop).
  6. `end`: Node kết thúc luồng.

- **Dữ liệu Edge:**
  - `from_node`: ID node nguồn.
  - `to_node`: ID node đích.
  - `condition_expr` (nếu từ node condition): Bật tắt điều kiện rẽ nhánh.

---

## 🔄 CƠ CHẾ SINH DỮ LIỆU RECIPE
Khi người dùng hoàn tất điền Form trên Workbench UI:
1. Client biên dịch toàn bộ Form thành đối tượng JSON chuẩn `Recipe`.
2. Gửi request sang `graph_lint(recipe)` để kiểm tra 4 quy tắc an toàn.
3. Lưu dữ liệu vào PostgreSQL bảng `wb.recipes` và `wb.recipe_versions`.
