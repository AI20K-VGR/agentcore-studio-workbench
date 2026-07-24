"""Publish Manager for Workbench (SWE owner — Thiệu Quang Minh).

Handles Publish / Rollback decision based on Scorecard evaluation from EvalHub.
Issue #19: Day 5 — SWE — Đấu nối publish flow + eval-gate wiring & version/rollback.
"""

from __future__ import annotations

from typing import Any
from studio_contracts import Scorecard, Recipe


async def handle_publish_request(
    agent_id: str,
    recipe: Recipe | Any,
    scorecard: Scorecard | Any,
) -> dict[str, Any]:
    """Xử lý lệnh xuất bản dựa trên Scorecard từ EvalHub.

    Checks if scorecard passes gate thresholds (verdict == "PASS" or pass_gate == True and score >= 0.85).
    """
    # Extract pass_gate / verdict status
    pass_gate = False
    overall_score = 0.0

    if hasattr(scorecard, "pass_gate"):
        pass_gate = bool(getattr(scorecard, "pass_gate"))
        overall_score = float(getattr(scorecard, "overall_score", 0.90))
    elif hasattr(scorecard, "gate"):
        pass_gate = (scorecard.gate.verdict == "PASS")
        overall_score = scorecard.aggregate.success_rate if hasattr(scorecard, "aggregate") else 0.90
    elif isinstance(scorecard, dict):
        pass_gate = scorecard.get("pass_gate", scorecard.get("gate", {}).get("verdict") == "PASS")
        overall_score = scorecard.get("overall_score", 0.90)

    if pass_gate and overall_score >= 0.85:
        score_percent = round(overall_score * 100, 1)
        return {
            "status": "SUCCESS",
            "published_version": "v1.0.0",
            "message": f"Xuất bản thành công! Điểm đánh giá: {score_percent}%",
        }
    else:
        score_percent = round(overall_score * 100, 1)
        return {
            "status": "ROLLBACKED",
            "active_version": "v0.9.0",
            "message": f"Xuất bản thất bại! Điểm đánh giá {score_percent}% dưới ngưỡng 85%.",
        }
