# backend/api/report.py

import csv
import io
import os
from datetime import timedelta
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


class DomainScore(BaseModel):
    score: int
    evidence: str
    suggestion: str


class ReportBody(BaseModel):
    summary: str
    domains: Dict[str, DomainScore]
    overall: Dict[str, Any]


@router.get("/feedback-sessions")
def get_feedback_sessions(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """저장된 연구 세션을 최근 생성 순서대로 조회한다."""
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
                    "speaker_confidence_label": session.speaker_confidence_label,
                    "speaker_uncertain": session.speaker_uncertain,
                    "get_commitment": session.get_commitment,
                    "probe_for_supporting_evidence": (
                        session.probe_for_supporting_evidence
                    ),
                    "teach_general_rules": session.teach_general_rules,
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
        print("=== DEBUG: feedback session query ERROR ===", repr(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Feedback session query failed: {exc}",
        ) from exc


@router.get("/feedback-sessions.csv")
def export_feedback_sessions_csv(
    db: Session = Depends(get_db),
):
    """
    feedback_session 테이블의 분석용 변수를 CSV로 내보낸다.
    created_at_utc와 created_at_kst를 함께 제공한다.
    """
    try:
        sessions = (
            db.query(FeedbackSession)
            .order_by(
                FeedbackSession.created_at.asc(),
                FeedbackSession.id.asc(),
            )
            .all()
        )

        text_buffer = io.StringIO()
        writer = csv.writer(text_buffer, lineterminator="\n")

        writer.writerow(
            [
                "id",
                "encounter_id",
                "supervisor_id",
                "trainee_id",
                "scenario_code",
                "scale_code",
                "trainee_level",
                "language",
                "speaker_mode",
                "speaker_confidence",
                "speaker_confidence_label",
                "speaker_uncertain",
                "get_commitment",
                "probe_for_supporting_evidence",
                "teach_general_rules",
                "reinforce_what_was_done_right",
                "correct_mistakes",
                "omp_total",
                "omp_scale",
                "omp_percent",
                "model_version",
                "prompt_version",
                "created_at_utc",
                "created_at_kst",
            ]
        )

        for session in sessions:
            created_at_utc = session.created_at
            created_at_kst = (
                created_at_utc + timedelta(hours=9)
                if created_at_utc
                else None
            )

            writer.writerow(
                [
                    session.id,
                    session.encounter_id,
                    session.supervisor_id,
                    session.trainee_id,
                    session.scenario_code,
                    session.scale_code,
                    session.trainee_level,
                    session.language,
                    session.speaker_mode,
                    session.speaker_confidence,
                    session.speaker_confidence_label,
                    session.speaker_uncertain,
                    session.get_commitment,
                    session.probe_for_supporting_evidence,
                    session.teach_general_rules,
                    session.reinforce_what_was_done_right,
                    session.correct_mistakes,
                    session.omp_total,
                    session.omp_scale,
                    session.omp_percent,
                    session.model_version,
                    session.prompt_version,
                    (
                        created_at_utc.isoformat()
                        if created_at_utc
                        else ""
                    ),
                    (
                        created_at_kst.isoformat()
                        if created_at_kst
                        else ""
                    ),
                ]
            )

        # Excel에서 한글이 깨지지 않도록 UTF-8 BOM을 추가한다.
        csv_bytes = ("\ufeff" + text_buffer.getvalue()).encode("utf-8")

        return StreamingResponse(
            io.BytesIO(csv_bytes),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": (
                    'attachment; filename="feedback_sessions.csv"'
                )
            },
        )

    except Exception as exc:
        print("=== DEBUG: CSV export ERROR ===", repr(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Feedback session CSV export failed: {exc}",
        ) from exc


def register_korean_font():
    try:
        font_path = r"C:\Windows\Fonts\malgun.ttf"
        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont("Malgun", font_path))
            return "Malgun"
    except Exception:
        pass
    return "Helvetica"


def wrap_text(text: str, width: int):
    words = text.split()
    lines = []
    current = ""

    for word in words:
        if len(current) + len(word) + 1 <= width:
            current = (current + " " + word).strip()
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


@router.post("/report")
def generate_report(body: ReportBody):
    """기존 PDF 보고서 생성 기능."""
    try:
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        _, height = A4
        font_name = register_korean_font()
        y = height - 40

        pdf.setFont(font_name, 16)
        pdf.drawString(40, y, "OSAD Feedback Report")
        y -= 24

        pdf.setFont(font_name, 12)
        pdf.drawString(40, y, "Summary:")
        y -= 16
        pdf.setFont(font_name, 10)

        for line in wrap_text(body.summary, 90):
            pdf.drawString(50, y, line)
            y -= 14

        y -= 10
        pdf.setFont(font_name, 12)
        pdf.drawString(40, y, "OSAD Domains:")
        y -= 16
        pdf.setFont(font_name, 10)

        for name, domain_score in body.domains.items():
            pdf.drawString(45, y, f"- {name}: {domain_score.score}")
            y -= 14

            for line in wrap_text(
                f"evidence: {domain_score.evidence}",
                92,
            ):
                pdf.drawString(55, y, line)
                y -= 12

            for line in wrap_text(
                f"suggestion: {domain_score.suggestion}",
                92,
            ):
                pdf.drawString(55, y, line)
                y -= 12

            y -= 6
            if y < 80:
                pdf.showPage()
                y = height - 40
                pdf.setFont(font_name, 10)

        y -= 10
        pdf.setFont(font_name, 12)
        pdf.drawString(40, y, "Overall:")
        y -= 16
        pdf.setFont(font_name, 10)

        for key in ["strengths", "improvements", "action_plan"]:
            values = body.overall.get(key, [])
            pdf.drawString(45, y, f"- {key}:")
            y -= 14

            for value in values:
                for line in wrap_text(f"• {value}", 95):
                    pdf.drawString(55, y, line)
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
