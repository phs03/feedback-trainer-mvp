# backend/api/report.py

import io
import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models.feedback_models import FeedbackSession


router = APIRouter(prefix="/api", tags=["report"])


# =========================
# PDF 보고서 입력 스키마
# =========================

class DomainScore(BaseModel):
    score: int
    evidence: str
    suggestion: str


class ReportBody(BaseModel):
    summary: str
    domains: Dict[str, DomainScore]
    overall: Dict[str, Any]


# =========================
# 연구 세션 조회 API
# =========================

@router.get("/feedback-sessions")
def get_feedback_sessions(
    limit: int = Query(
        default=20,
        ge=1,
        le=200,
        description="조회할 최대 세션 수",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="건너뛸 세션 수",
    ),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    feedback_session 테이블에 저장된 연구 세션을
    최근 생성 순서대로 조회한다.
    """

    try:
        total = db.query(FeedbackSession).count()

        sessions = (
            db.query(FeedbackSession)
            .order_by(
                FeedbackSession.created_at.desc(),
                FeedbackSession.id.desc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

        items = []

        for session in sessions:
            items.append(
                {
                    "id": session.id,
                    "encounter_id": session.encounter_id,
                    "supervisor_id": session.supervisor_id,
                    "trainee_id": session.trainee_id,
                    "scenario_code": session.scenario_code,
                    "scale_code": session.scale_code,
                    "trainee_level": session.trainee_level,
                    "language": session.language,
                    "speaker_mode": session.speaker_mode,
                    "speaker_confidence": session.speaker_confidence,
                    "speaker_confidence_label": (
                        session.speaker_confidence_label
                    ),
                    "speaker_uncertain": session.speaker_uncertain,
                    "get_commitment": session.get_commitment,
                    "probe_for_supporting_evidence": (
                        session.probe_for_supporting_evidence
                    ),
                    "teach_general_rules": (
                        session.teach_general_rules
                    ),
                    "reinforce_what_was_done_right": (
                        session.reinforce_what_was_done_right
                    ),
                    "correct_mistakes": session.correct_mistakes,
                    "omp_total": session.omp_total,
                    "omp_scale": session.omp_scale,
                    "omp_percent": session.omp_percent,
                    "model_version": session.model_version,
                    "prompt_version": session.prompt_version,
                    "created_at": (
                        session.created_at.isoformat()
                        if session.created_at
                        else None
                    ),
                }
            )

        return {
            "status": "ok",
            "total": total,
            "limit": limit,
            "offset": offset,
            "count": len(items),
            "items": items,
        }

    except Exception as exc:
        print(
            "=== DEBUG: /api/feedback-sessions ERROR ===",
            repr(exc),
        )

        raise HTTPException(
            status_code=500,
            detail=f"Feedback session query failed: {exc}",
        ) from exc


# =========================
# PDF 생성 보조 함수
# =========================

def register_korean_font():
    """
    Windows의 맑은 고딕 폰트를 등록한다.
    사용할 수 없으면 Helvetica를 사용한다.
    """

    try:
        font_path = r"C:\Windows\Fonts\malgun.ttf"

        if os.path.exists(font_path):
            pdfmetrics.registerFont(
                TTFont("Malgun", font_path)
            )
            return "Malgun"

    except Exception:
        pass

    return "Helvetica"


def wrap_text(text: str, width: int):
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        if len(current_line) + len(word) + 1 <= width:
            current_line = (
                current_line + " " + word
            ).strip()
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return lines


# =========================
# 기존 PDF 보고서 생성 API
# =========================

@router.post("/report")
def generate_report(body: ReportBody):
    try:
        buffer = io.BytesIO()

        pdf = canvas.Canvas(
            buffer,
            pagesize=A4,
        )

        _, height = A4
        font_name = register_korean_font()

        y = height - 40

        pdf.setFont(font_name, 16)
        pdf.drawString(
            40,
            y,
            "OSAD Feedback Report",
        )
        y -= 24

        # Summary
        pdf.setFont(font_name, 12)
        pdf.drawString(
            40,
            y,
            "Summary:",
        )
        y -= 16

        pdf.setFont(font_name, 10)

        for line in wrap_text(body.summary, 90):
            pdf.drawString(
                50,
                y,
                line,
            )
            y -= 14

        # Domains
        y -= 10
        pdf.setFont(font_name, 12)
        pdf.drawString(
            40,
            y,
            "OSAD Domains:",
        )
        y -= 16

        pdf.setFont(font_name, 10)

        for name, domain_score in body.domains.items():
            pdf.drawString(
                45,
                y,
                f"- {name}: {domain_score.score}",
            )
            y -= 14

            for line in wrap_text(
                f"evidence: {domain_score.evidence}",
                92,
            ):
                pdf.drawString(
                    55,
                    y,
                    line,
                )
                y -= 12

            for line in wrap_text(
                f"suggestion: {domain_score.suggestion}",
                92,
            ):
                pdf.drawString(
                    55,
                    y,
                    line,
                )
                y -= 12

            y -= 6

            if y < 80:
                pdf.showPage()
                y = height - 40
                pdf.setFont(font_name, 10)

        # Overall
        y -= 10
        pdf.setFont(font_name, 12)
        pdf.drawString(
            40,
            y,
            "Overall:",
        )
        y -= 16

        pdf.setFont(font_name, 10)

        for key in [
            "strengths",
            "improvements",
            "action_plan",
        ]:
            values = body.overall.get(key, [])

            pdf.drawString(
                45,
                y,
                f"- {key}:",
            )
            y -= 14

            for value in values:
                for line in wrap_text(
                    f"• {value}",
                    95,
                ):
                    pdf.drawString(
                        55,
                        y,
                        line,
                    )
                    y -= 12

            y -= 4

            if y < 80:
                pdf.showPage()
                y = height - 40
                pdf.setFont(font_name, 10)

        pdf.showPage()
        pdf.save()

        buffer.seek(0)

        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    "attachment; filename=OSAD_Report.pdf"
                )
            },
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"PDF generation failed: {exc}",
        ) from exc