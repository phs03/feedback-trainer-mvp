# backend/api/coach_eval.py

import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["coach_eval"])

# ---------- SQLite 초기화 ----------

DB_PATH = Path("coach_evals.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS coach_report_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            encounter_id TEXT,
            scenario_code TEXT,
            scale_code TEXT,
            model_version TEXT,
            helpful_score INTEGER,
            helpful_flags TEXT,
            comment TEXT,
            created_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


init_db()


# ---------- Pydantic 모델 ----------

class CoachEvalRequest(BaseModel):
    """
    코칭 리포트가 얼마나 도움이 되었는지에 대한 사용자 평가 요청 모델
    """
    encounter_id: str = Field(..., description="feedback 세션을 식별하는 ID")
    scenario_code: Optional[str] = Field(
        default="EM_DEBRIEF",
        description="상황 코드 (예: EM_DEBRIEF)"
    )
    scale_code: Optional[str] = Field(
        default="OSAD_DEBRIEFER",
        description="스케일 코드 (예: OSAD_DEBRIEFER)"
    )
    model_version: Optional[str] = Field(
        default=None,
        description="코칭 리포트를 생성한 모델/프롬프트 버전"
    )
    helpful_score: int = Field(
        ...,
        ge=1,
        le=5,
        description="코칭 리포트의 도움 정도 (1~5 리커트)"
    )
    helpful_flags: Optional[List[str]] = Field(
        default=None,
        description="도움이 된 부분 체크박스 (예: ['strengths', 'script_next_time'])"
    )
    comment: Optional[str] = Field(
        default=None,
        description="추가 코멘트 (선택)"
    )


class CoachEvalResponse(BaseModel):
    status: str = "ok"


# ---------- 라우터 ----------

@router.post("/feedback/coach-eval", response_model=CoachEvalResponse)
async def save_coach_eval(payload: CoachEvalRequest):
    """
    코칭 리포트에 대한 사용자의 평가를 저장한다.
    추후 모델/프롬프트 개선 및 릴리즈 의사결정에 활용.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO coach_report_feedback (
                encounter_id,
                scenario_code,
                scale_code,
                model_version,
                helpful_score,
                helpful_flags,
                comment,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.encounter_id,
                payload.scenario_code,
                payload.scale_code,
                payload.model_version,
                payload.helpful_score,
                json.dumps(payload.helpful_flags) if payload.helpful_flags else None,
                payload.comment,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        return CoachEvalResponse(status="ok")

    except Exception as e:
        print("=== ERROR in /feedback/coach-eval ===", repr(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save coach evaluation: {e}",
        )
