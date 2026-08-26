"""Local test-infra override, scoped to THIS directory only.

Windows defaults `asyncio` to `ProactorEventLoop`, which `psycopg` async refuses ("Psycopg cannot
use the 'ProactorEventLoop' to run in async mode"). The kit-root `conftest.py` (repo cha) không có
fix này, và `apps/studio/tests/conftest.py` chỉ áp dụng cho thư mục đó (pytest merge `conftest.py`
theo cây thư mục, không lan ngang sang `packages/workbench/tests/`) — nên các test DB thật ở đây
(`test_publish.py`, `test_wb_schema.py`) trước giờ luôn bị skip khi thiếu DSN, chưa từng thật sự
chạy trên Windows để lộ lỗ hổng này. Thêm cùng fixture ở đây, cùng mẫu đã áp cho `apps/studio`.

File này CỐ Ý không giữ helper dùng chung nào (`ANKOR_ID`/`assert_finding_status` đã gỡ,
workbench#53). Một lượt `/simplify` từng gom chúng vào đây, và hai file mới của workbench#48 đổi
sang `from conftest import ...` — nhưng workspace có 6 file `conftest.py` và `tests/` không phải
package, nên tên module đó bị tranh chấp: `mypy packages apps` (job `lint` của kit) đỏ 4 lỗi, và
`pytest` ở gốc kit ABORT cả lượt thu thập. Cả hai vô hình với CI của repo con.

Convention của package này là mỗi file test tự khai hằng/helper của nó — 8 file khác đã làm vậy từ
trước (`test_publish.py`, `test_wb_schema.py`, `test_wiring_d4/d7/d8/d9.py`, ...). Thêm helper dùng
chung vào đây là mở lại đúng cửa đó.
"""

from __future__ import annotations

import asyncio
import sys

import pytest


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()
