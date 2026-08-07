"""Playground dev server (D15, issue kit#102, spec SWE) — `bấm Test 1 recipe
→ interpreter chạy → trace viewer hiện`.

Đứng NGOÀI `src/studio_workbench/` cố ý, giống `scripts/smoke_eval_d6.py` ở
repo root: cả hai đều compose nhiều quadrant (`studio_engine`, `studio_workbench`,
`studio_contracts`) trong 1 script, và `.importlinter`'s `layers` contract chỉ
soi import graph BÊN TRONG mỗi root package (`src/studio_workbench/...`) — một
script rời không thuộc package nào thì không lọt vào graph đó. Nếu file này bị
dọn vào trong `src/studio_workbench/`, `uv run lint-imports` sẽ đỏ ngay (quadrant
`studio_workbench` không được phép import `studio_engine`, xem `.importlinter`).

Vì sao script này tồn tại (thay vì gọi thẳng `apps/studio`): `apps/studio`
(composition root FastAPI thật) hiện chưa có route nào (`pyproject.toml` của
nó ghi "Owner: mentor") và không nằm trong phạm vi WRITE của issue #102
(`agentcore-studio-workbench (+ agentcore-studio-web)`). Server này là bản
COMPOSE-TẠI-CHỖ cho riêng Playground local dev — không phải bản thay thế cho
`apps/studio`; khi route thật ở đó xuất hiện, `apps/web/src/playground/api.ts`
chỉ cần đổi `VITE_PLAYGROUND_API_URL` là trỏ sang, không đổi hình dạng gọi.

Collaborators dưới đây:
- `kb_search` = `StaticKbSearch` THẬT của DE (`studio_kb.static_search`, 140 chunk/42 doc
  Callisto thật, 2 tenant ankor/borea) — KHÔNG phải stub tự chế. Đổi từ 1 `PlaygroundKbSearch`
  3-câu tự viết sang đúng class AIE-1 đang dùng trong `agentcore-studio-engine` PR#19
  (`scripts/run_real_batch.py`, D15 #101, đã verify chạy đúng "schema OK"/"C-1 OK" trước khi
  đổi ở đây) — để Playground và batch-thật của AIE-1 nối vào ĐÚNG MỘT nguồn KB, không phải 2
  bản dữ liệu khác nhau tình cờ trùng tên. Cùng lý do `.importlinter` cho phép: script này
  đứng ngoài `src/studio_workbench/` (xem đoạn trên), giống hệt tiền lệ
  `scripts/measure_chunk_embed.py` (D11) và `agentcore-studio-engine/scripts/run_real_batch.py`
  (D15) — cả 2 cũng import `studio_kb` từ 1 file rời ngoài package.
- `llm` = `CitingEchoLLM`, demo-only, cùng tinh thần `studio_engine.demo_stubs` (đã tự nhận
  "Day 3 demo-only... Day 6 replaces with real composition") — chưa có gateway LLM thật nào để
  nối. Logic trích dẫn giống hệt `_CitingLLM` của AIE-1 (PR#19): dedupe rồi cite LẠI TẤT CẢ
  chunk_id thật sự có trong prompt, không tự bịa câu trả lời.

⚠️ **`section_roles` CHƯA server-resolve** (khác `tenant_id`) — đây không phải sơ suất của file
này, mà là nợ mở có tên thật của cả team: `docs/backlog.yaml` **FENCE-SEAM-1** ("the real
KbSearch impl must resolve section_roles server-side, not trust node.params, to avoid T6
label-spoof"), ghi lại trong chính design-note D15 của AIE-1. `section_roles` ở đây vẫn đọc
nguyên từ `node.params` mà client (canvas) khai — client tự chọn checkbox nào thì
`StaticKbSearch` lọc đúng bấy nhiêu, không hơn.

`timeline_text` trên cả 2 response (POST/GET) là output THẬT của `render_timeline()`
(`studio_kb.trace_reader`, DE — PR#16 D15 #100), gọi trực tiếp trên `RunResult.events` của
chính run vừa chạy, `expected=walk_from_dag(recipe.dag)` (không phải `EXPECTED_WALK` cố định 4
node) để soi đúng bất kỳ canvas nào. Không phải bản sao chép — verify bằng cách gọi thẳng hàm
thật của DE trên events tự sinh ra, và DE không cần đổi gì để việc này chạy (hàm vốn đã nhận
`list[TraceEvent]` chung chung, không khoá vào `PgTraceReader`/Postgres).

`score` trên cả 2 response — output THẬT của `score_run_from_trace()` (`studio_evalhub.run_report`,
AIE-2 — PR#15 D15 #103), CÙNG cơ chế với `timeline_text`. Điểm khác biệt: `studio_evalhub` chưa
merge PR#15 tính đến lúc file này viết, nên `run_report` được import trong `try/except ImportError`
ở module-level — thiếu package đó KHÔNG được phép làm sập cả server (3/4 phần SWE/AIE-1/DE vẫn
phải chạy bình thường). Sau khi AIE-2 merge + `git submodule update packages/evalhub`, field `score`
tự nhiên có giá trị thật ở lần chạy TIẾP THEO — không cần sửa lại file này. `_case_by_id` là hàm
private (`_`-prefix) của họ — chấp nhận giòn (fragile) đổi lấy 1 lần gọi, ghi rõ ở đây để ai đọc
sau không tưởng đây là API công khai.

Chạy: `uv run python packages/workbench/dev_playground_server.py [port=8787]`
"""

from __future__ import annotations

import asyncio
import importlib
import json
import re
import sys
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from pydantic import ValidationError
from studio_contracts import Recipe, TraceEvent
from studio_engine import interpreter
from studio_engine.demo_stubs import EmptyEmbedding
from studio_kb.doc_factory import TENANT_IDS
from studio_kb.static_search import StaticKbSearch
from studio_kb.trace_reader import render_timeline, walk_from_dag

from studio_workbench.tenant_wall import resolve_session

try:
    # PR evalhub#15 (D15 #103, AIE-2) — chưa merge tính đến lúc viết file này. Guard bằng
    # try/except NGAY Ở MODULE LEVEL: nếu để `ImportError` văng thẳng, toàn bộ server sập lúc
    # khởi động (kể cả phần SWE/AIE-1/DE đang chạy tốt) chỉ vì thiếu 1 package của người khác
    # chưa merge — đó là lý do KHÔNG import thẳng như 3 collaborator kia ở trên.
    #
    # `importlib.import_module()` (chuỗi, KHÔNG phải `from studio_evalhub.run_report import
    # ...` tĩnh) cố ý: mypy strict resolve import tĩnh ở compile-time và sẽ đỏ thật
    # ("Cannot find implementation... studio_evalhub.run_report") ngay cả khi bọc try/except
    # runtime — package đó THẬT SỰ chưa tồn tại, không phải mypy nhầm. Import động là cách
    # chuẩn cho optional dependency, không phải `type: ignore` che lỗi thật.
    _run_report: Any = importlib.import_module("studio_evalhub.run_report")
except ImportError:
    _run_report = None

# Nguồn sự thật DUY NHẤT cho UUID tenant demo — import thẳng từ `studio_kb.doc_factory`
# (DE) thay vì hand-copy lại như bản trước, để không thể lệch với dữ liệu `StaticKbSearch`
# thật sự nạp. `apps/web/src/recipe/contract.ts` (ANKOR_ID/BOREA_ID) vẫn phải hand-copy phía
# TS (không import Python qua được biên ngôn ngữ) — 2 bên khớp nhau vì cùng quy ước
# "chữ đầu = tên tenant" ghi trong chính docstring của `TENANT_IDS`.
ANKOR_ID = TENANT_IDS["ankor"]
BOREA_ID = TENANT_IDS["borea"]

_CHUNK_ID_RE = re.compile(r"\[([\w#-]+)\]")


class CitingEchoLLM:
    """`LLM` demo — không gọi model thật (INV-4 vẫn giữ nguyên cho CI/test,
    server này chỉ chạy tay lúc dev). Cùng logic với `_CitingLLM` của AIE-1
    (`agentcore-studio-engine` PR#19, D15 #101): dedupe rồi trích dẫn LẠI TẤT
    CẢ `chunk_id` thật sự có trong prompt (`executors.py::build_prompt` in
    mỗi excerpt dạng `[id]` đứng riêng 1 dòng) — không chỉ chunk đầu tiên như
    bản trước ở đây, và không tự bịa câu trả lời ngoài việc trích dẫn lại."""

    async def complete(self, prompt: str, **kwargs: object) -> str:
        del kwargs
        if "(không có đoạn trích nào được truy xuất)" in prompt:
            return "Không có đoạn trích nào được truy xuất, không thể trả lời."
        ids = list(dict.fromkeys(_CHUNK_ID_RE.findall(prompt)))
        if not ids:
            return "Không có đoạn trích nào được truy xuất, không thể trả lời."
        cited = " ".join(f"[{cid}]" for cid in ids)
        return f"Theo tài liệu thật đã truy xuất, câu trả lời có căn cứ tại {cited}."


class InMemoryTraceWriter:
    """`TraceWriter` demo — thay `PgTraceWriter` (cần Postgres thật). Giữ
    nguyên hợp đồng đọc lại của `PgTraceReader.read_run(run_id, tenant_id)`
    (`packages/kb/src/studio_kb/trace_reader.py`): lọc theo CẢ `run_id` LẪN
    `tenant_id`, không phải chỉ `run_id` — một request đọc trace bằng đúng
    `run_id` nhưng tenant khác vẫn phải về rỗng (cùng tinh thần fence, ở tầng
    đọc thay vì tầng ghi)."""

    def __init__(self) -> None:
        self._by_run: dict[str, list[TraceEvent]] = {}

    async def write(self, event: TraceEvent) -> None:
        self._by_run.setdefault(event.run_id, []).append(event)

    def read_run(self, run_id: str, tenant_id: UUID) -> list[TraceEvent]:
        return [e for e in self._by_run.get(run_id, []) if e.tenant_id == tenant_id]


@dataclass(frozen=True, slots=True)
class _DevSessionContext:
    """`SessionContext` demo — Playground chưa có auth thật (D15). Tenant lấy
    từ lựa chọn tenant NGƯỜI DÙNG bấm trên form canvas (`recipe.tenant_id`),
    coi như "đang đăng nhập với tư cách tenant X" — CÙNG kiểu dev-stub đã có
    sẵn ở `apps/studio/src/studio_app/middleware.py` (tự nhận "DEV-TIME STUB —
    NOT production-grade" trong chính comment của nó). Khi auth thật lên
    (ngoài phạm vi D15), điểm build session này là chỗ DUY NHẤT phải đổi —
    `interpreter.run()` xuôi dòng không đổi gì."""

    tenant_id: UUID
    user: str
    roles: list[str]


_TRACE_WRITER = InMemoryTraceWriter()
# `render_timeline()` THẬT của DE (`studio_kb.trace_reader`, PR#16 D15 #100) — không phải bản
# tự viết. Tính 1 lần ngay sau `interpreter.run()` (đã có `recipe.dag` trong tay để suy đúng
# `walk_from_dag`) rồi lưu lại, vì `do_GET` không giữ `recipe` — tránh phải tái tạo `expected`
# từ chính `events` (vòng lặp, không phải nguồn kỳ vọng thật).
_TIMELINE_TEXT: dict[str, str] = {}
_SCORE: dict[str, dict[str, Any]] = {}

# Case demo cố định — recipe mẫu (sample.ts) hỏi đúng câu hỏi của case này. KHÔNG có ánh xạ
# golden_set_ref -> case_id thật (đó là việc của AIE-2/D16), nên 1 recipe tự do không khớp
# case này thì `_score_run` trả về message giải thích, không phải điểm bịa.
_DEMO_CASE_ID = "SC-01"


def _score_run(events: list[TraceEvent]) -> dict[str, Any]:
    """Chấm `events` bằng `score_run_from_trace()` THẬT của AIE-2 khi có sẵn (PR#15 merge).
    Không bao giờ raise ra ngoài — mọi nhánh hỏng (chưa merge, case không khớp, trace không
    chấm được) đều trả về 1 dict giải thích, để 3 phần kia (SWE/AIE-1/DE) không bị kéo sập
    theo chỉ vì phần chấm điểm hỏng."""
    if _run_report is None:
        return {
            "available": False,
            "message": "PR evalhub#15 (AIE-2, D15 #103) chưa merge/chưa `git submodule update packages/evalhub`.",
        }
    try:
        case = _run_report._case_by_id(_DEMO_CASE_ID)
        answer = _run_report.answer_from_trace(events)
        result = _run_report.score_run_from_trace(case, events)
    except (LookupError, ValueError) as exc:
        return {"available": True, "scored": False, "message": f"{type(exc).__name__}: {exc}"}
    return {
        "available": True,
        "scored": True,
        "case_id": str(result.case_id),
        "success": bool(result.success),
        "citation_accuracy": float(result.citation_accuracy),
        "citations": list(answer.citations),
    }


async def _execute_run(recipe: Recipe) -> interpreter.RunResult:
    session = resolve_session({"tenant_id": recipe.tenant_id, "user": "playground-dev-user", "roles": []})
    # `_DevSessionContext` thay vì dùng thẳng `ResolvedContext` (dù nó đã khớp
    # Protocol) — tách riêng để chỗ dev-stub (docstring ở trên) đứng MỘT nơi,
    # không lẫn với `tenant_wall.resolve_session`'s hợp đồng thật (P7 seam).
    session_context = _DevSessionContext(tenant_id=session.tenant_id, user=session.user, roles=session.roles)
    return await interpreter.run(
        recipe,
        session_context=session_context,
        kb_search=StaticKbSearch(),
        llm=CitingEchoLLM(),
        embedding=EmptyEmbedding(),
        trace_writer=_TRACE_WRITER,
    )


def _event_json(event: TraceEvent) -> dict[str, Any]:
    return event.model_dump(mode="json")


class _Handler(BaseHTTPRequestHandler):
    server_version = "PlaygroundDev/0.1"

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # Dev-only CORS — Vite dev server (origin khác cổng) gọi thẳng qua
        # `fetch()`, không qua proxy (xem `apps/web/src/playground/api.ts`).
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message})

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        sys.stderr.write(f"[playground-dev] {self.address_string()} - {fmt % args}\n")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path != "/api/runs":
            self._error(404, f"no route POST {path}")
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            self._error(400, f"body không phải JSON hợp lệ: {exc}")
            return

        recipe_json = body.get("recipe") if isinstance(body, dict) else None
        if recipe_json is None:
            self._error(400, "thiếu field `recipe` trong body")
            return

        try:
            recipe = Recipe.model_validate(recipe_json)
        except ValidationError as exc:
            # Playground UI đã chặn export/test khi `graph_lint()` đỏ (fail-closed
            # phía client) — cái này là belt-and-suspenders phía server, không
            # phải đường vòng: `Recipe.model_validate()` là Pydantic, không phải
            # `graph_lint`'s 7 luật, nên vẫn có thể bắt khác loại lỗi (thiếu field...).
            self._error(400, f"recipe không qua Recipe.model_validate(): {exc.errors()!r}")
            return

        try:
            result = asyncio.run(_execute_run(recipe))
        except PermissionError as exc:
            self._error(403, str(exc))
            return
        except NotImplementedError as exc:
            # `condition`/`hitl-pause` vẫn NotImplementedError phía AIE-1 (D15) —
            # trả lỗi rõ ràng thay vì 500 trần trụi khi 1 recipe lỡ đi qua node đó.
            self._error(501, f"node type chưa implement (spec AIE-1): {exc}")
            return
        except Exception as exc:  # noqa: BLE001
            self._error(500, f"interpreter.run() lỗi: {type(exc).__name__}: {exc}")
            return

        # `walk_from_dag(recipe.dag)` — chuỗi kỳ vọng suy từ CHÍNH recipe vừa chạy, không phải
        # `EXPECTED_WALK` mặc định (đúng khuyến nghị của DE cho recipe đi động, không cố định
        # 4-node): 1 canvas tuỳ ý (có `condition`/`hitl-pause`...) vẫn được `render_timeline` soi
        # đúng, không báo "gap" giả vì so nhầm khuôn.
        _TIMELINE_TEXT[result.run_id] = render_timeline(result.events, expected=walk_from_dag(recipe.dag))
        _SCORE[result.run_id] = _score_run(result.events)

        self._send_json(
            200,
            {
                "run_id": result.run_id,
                "agent_id": recipe.agent_id,
                "tenant_id": str(recipe.tenant_id),
                "events": [_event_json(e) for e in result.events],
                "timeline_text": _TIMELINE_TEXT[result.run_id],
                "score": _SCORE[result.run_id],
            },
        )

    def do_GET(self) -> None:  # noqa: N802
        split = urlsplit(self.path)
        parts = split.path.strip("/").split("/")
        if len(parts) != 3 or parts[0:2] != ["api", "runs"]:
            self._error(404, f"no route GET {split.path}")
            return
        run_id = parts[2]
        qs = parse_qs(split.query)
        tenant_values = qs.get("tenant_id")
        tenant_raw = tenant_values[0] if tenant_values else None
        if not tenant_raw:
            self._error(400, "thiếu query param `tenant_id` — trace đọc lại cũng phải qua fence tenant")
            return
        try:
            tenant_id = UUID(tenant_raw)
        except ValueError:
            self._error(400, f"tenant_id không phải UUID hợp lệ: {tenant_raw!r}")
            return

        events = _TRACE_WRITER.read_run(run_id, tenant_id)
        # `timeline_text` chỉ trả khi `events` (đã lọc tenant) không rỗng — 1 run chỉ thuộc đúng
        # 1 tenant nên text tính lúc POST vốn đã tenant-scoped, nhưng vẫn gate qua `events` ở đây
        # để 1 request tenant sai không đọc được text của tenant khác qua đường tắt này.
        timeline_text = _TIMELINE_TEXT.get(run_id) if events else None
        score = _SCORE.get(run_id) if events else None
        self._send_json(
            200,
            {
                "run_id": run_id,
                "found": bool(events),
                "agent_id": events[0].agent_id if events else None,
                "tenant_id": str(tenant_id),
                "events": [_event_json(e) for e in events],
                "timeline_text": timeline_text,
                "score": score,
            },
        )


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    print(
        f"[playground-dev] listening on http://127.0.0.1:{port}  (POST /api/runs, GET /api/runs/<run_id>?tenant_id=...)"
    )
    print(f"[playground-dev] tenant demo: ankor={ANKOR_ID}  borea={BOREA_ID}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
