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
from backend.models.feedback_models import (
    FeedbackSession,
    HumanOMPAssessment,
)

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




# =========================
# 연구 진행 현황 요약
# =========================

@router.get("/research-status")
def get_research_status(
    required_raters: int = Query(
        default=2,
        ge=1,
        le=10,
        description="세션당 필요한 인간 평가자 수",
    ),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    연구 진행 상황과 데이터 완성도를 요약한다.
    """

    try:
        sessions = db.query(FeedbackSession).all()
        ratings = db.query(HumanOMPAssessment).all()

        rating_counts = {}
        unique_raters = set()

        for rating in ratings:
            rating_counts[rating.encounter_id] = (
                rating_counts.get(rating.encounter_id, 0) + 1
            )
            unique_raters.add(rating.rater_id)

        total_sessions = len(sessions)

        sessions_with_any_human_rating = sum(
            1
            for session in sessions
            if rating_counts.get(session.encounter_id, 0) >= 1
        )

        sessions_with_required_raters = sum(
            1
            for session in sessions
            if rating_counts.get(session.encounter_id, 0)
            >= required_raters
        )

        sessions_without_human_rating = sum(
            1
            for session in sessions
            if rating_counts.get(session.encounter_id, 0) == 0
        )

        speaker_uncertain_sessions = sum(
            1
            for session in sessions
            if bool(session.speaker_uncertain)
        )

        low_confidence_sessions = sum(
            1
            for session in sessions
            if (
                session.speaker_confidence is None
                or session.speaker_confidence < 0.6
            )
        )

        completion_percent = (
            round(
                sessions_with_required_raters
                / total_sessions
                * 100,
                1,
            )
            if total_sessions > 0
            else 0.0
        )

        return {
            "status": "ok",
            "required_raters_per_session": required_raters,
            "total_feedback_sessions": total_sessions,
            "total_human_ratings": len(ratings),
            "unique_human_raters": len(unique_raters),
            "sessions_with_any_human_rating": (
                sessions_with_any_human_rating
            ),
            "sessions_with_required_raters": (
                sessions_with_required_raters
            ),
            "sessions_without_human_rating": (
                sessions_without_human_rating
            ),
            "speaker_uncertain_sessions": (
                speaker_uncertain_sessions
            ),
            "low_confidence_sessions": (
                low_confidence_sessions
            ),
            "rating_completion_percent": completion_percent,
        }

    except Exception as exc:
        print(
            "=== DEBUG: /api/research-status ERROR ===",
            repr(exc),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Research status query failed: {exc}",
        ) from exc



# =========================
# 연구 미완료·품질점검 세션 목록
# =========================

@router.get("/research-pending")
def get_research_pending_sessions(
    required_raters: int = Query(
        default=2,
        ge=1,
        le=10,
        description="세션당 필요한 인간 평가자 수",
    ),
    include_completed: bool = Query(
        default=False,
        description="완료된 세션도 포함할지 여부",
    ),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    인간 평가가 부족하거나 화자 분석 품질점검이 필요한 세션을 반환한다.
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

        ratings = db.query(HumanOMPAssessment).all()

        ratings_by_encounter = {}

        for rating in ratings:
            ratings_by_encounter.setdefault(
                rating.encounter_id,
                [],
            ).append(rating)

        items = []

        for session in sessions:
            session_ratings = ratings_by_encounter.get(
                session.encounter_id,
                [],
            )

            rater_ids = sorted(
                {
                    rating.rater_id
                    for rating in session_ratings
                }
            )
            rating_count = len(rater_ids)
            missing_rater_count = max(
                0,
                required_raters - rating_count,
            )

            needs_rating = rating_count < required_raters
            needs_speaker_review = bool(
                session.speaker_uncertain
            ) or (
                session.speaker_confidence is None
                or session.speaker_confidence < 0.6
            )

            completed = (
                not needs_rating
                and not needs_speaker_review
            )

            if completed and not include_completed:
                continue

            reasons = []

            if needs_rating:
                reasons.append(
                    f"인간 평가 {missing_rater_count}건 부족"
                )

            if bool(session.speaker_uncertain):
                reasons.append("화자 역할 추론 불확실")

            if session.speaker_confidence is None:
                reasons.append("화자 신뢰도 없음")
            elif session.speaker_confidence < 0.6:
                reasons.append("화자 신뢰도 낮음")

            items.append(
                {
                    "feedback_session_id": session.id,
                    "encounter_id": session.encounter_id,
                    "supervisor_id": session.supervisor_id,
                    "trainee_id": session.trainee_id,
                    "omp_total": session.omp_total,
                    "omp_percent": session.omp_percent,
                    "speaker_confidence": (
                        session.speaker_confidence
                    ),
                    "speaker_confidence_label": (
                        session.speaker_confidence_label
                    ),
                    "speaker_uncertain": (
                        session.speaker_uncertain
                    ),
                    "human_rating_count": rating_count,
                    "required_raters": required_raters,
                    "missing_rater_count": (
                        missing_rater_count
                    ),
                    "rater_ids": rater_ids,
                    "needs_rating": needs_rating,
                    "needs_speaker_review": (
                        needs_speaker_review
                    ),
                    "completed": completed,
                    "reasons": reasons,
                    "created_at": (
                        session.created_at.isoformat()
                        if session.created_at
                        else None
                    ),
                }
            )

        pending_count = sum(
            1
            for item in items
            if not item["completed"]
        )

        return {
            "status": "ok",
            "required_raters_per_session": required_raters,
            "include_completed": include_completed,
            "count": len(items),
            "pending_count": pending_count,
            "items": items,
        }

    except Exception as exc:
        print(
            "=== DEBUG: /api/research-pending ERROR ===",
            repr(exc),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Research pending query failed: {exc}",
        ) from exc


# =========================
# AI-인간 결합 연구 분석 CSV
# =========================

@router.get("/research-analysis.csv")
def export_research_analysis_csv(
    db: Session = Depends(get_db),
):
    """
    AI 평가와 인간 평가를 encounter_id 기준으로 결합해 CSV로 내보낸다.

    한 인간 평가당 한 행을 생성하는 long format이다.
    평가자 2명이 같은 세션을 평가하면 같은 encounter_id로 2행이 생성된다.
    인간 평가가 아직 없는 AI 세션도 포함하며 human_* 값은 비워 둔다.
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

        ratings = (
            db.query(HumanOMPAssessment)
            .order_by(
                HumanOMPAssessment.encounter_id.asc(),
                HumanOMPAssessment.rater_id.asc(),
            )
            .all()
        )

        ratings_by_encounter = {}

        for rating in ratings:
            ratings_by_encounter.setdefault(
                rating.encounter_id,
                [],
            ).append(rating)

        text_buffer = io.StringIO()
        writer = csv.writer(
            text_buffer,
            lineterminator="\n",
        )

        writer.writerow(
            [
                "encounter_id",
                "feedback_session_id",
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
                "ai_get_commitment",
                "ai_probe_for_supporting_evidence",
                "ai_teach_general_rules",
                "ai_reinforce_what_was_done_right",
                "ai_correct_mistakes",
                "ai_omp_total",
                "ai_omp_scale",
                "ai_omp_percent",
                "rater_id",
                "human_get_commitment",
                "human_probe_for_supporting_evidence",
                "human_teach_general_rules",
                "human_reinforce_what_was_done_right",
                "human_correct_mistakes",
                "human_omp_total",
                "human_omp_scale",
                "human_omp_percent",
                "human_comment",
                "ai_minus_human_get_commitment",
                "ai_minus_human_probe_for_supporting_evidence",
                "ai_minus_human_teach_general_rules",
                "ai_minus_human_reinforce_what_was_done_right",
                "ai_minus_human_correct_mistakes",
                "ai_minus_human_total",
                "model_version",
                "prompt_version",
                "session_created_at_utc",
                "session_created_at_kst",
                "human_rating_created_at_utc",
                "human_rating_created_at_kst",
                "human_rating_updated_at_utc",
                "human_rating_updated_at_kst",
            ]
        )

        def to_iso(value):
            return value.isoformat() if value else ""

        def to_kst_iso(value):
            if not value:
                return ""
            return (value + timedelta(hours=9)).isoformat()

        def difference(ai_value, human_value):
            if ai_value is None or human_value in ("", None):
                return ""
            return ai_value - human_value

        for session in sessions:
            session_ratings = ratings_by_encounter.get(
                session.encounter_id,
                [],
            )

            rows_to_write = session_ratings or [None]

            for rating in rows_to_write:
                if rating is None:
                    rater_id = ""
                    human_get_commitment = ""
                    human_probe = ""
                    human_general_rules = ""
                    human_reinforcement = ""
                    human_correction = ""
                    human_total = ""
                    human_scale = ""
                    human_percent = ""
                    human_comment = ""
                    rating_created_at = None
                    rating_updated_at = None
                else:
                    rater_id = rating.rater_id
                    human_get_commitment = rating.get_commitment
                    human_probe = (
                        rating.probe_for_supporting_evidence
                    )
                    human_general_rules = (
                        rating.teach_general_rules
                    )
                    human_reinforcement = (
                        rating.reinforce_what_was_done_right
                    )
                    human_correction = rating.correct_mistakes
                    human_total = rating.omp_total
                    human_scale = rating.omp_scale
                    human_percent = rating.omp_percent
                    human_comment = rating.comment or ""
                    rating_created_at = rating.created_at
                    rating_updated_at = rating.updated_at

                writer.writerow(
                    [
                        session.encounter_id,
                        session.id,
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
                        rater_id,
                        human_get_commitment,
                        human_probe,
                        human_general_rules,
                        human_reinforcement,
                        human_correction,
                        human_total,
                        human_scale,
                        human_percent,
                        human_comment,
                        difference(
                            session.get_commitment,
                            human_get_commitment,
                        ),
                        difference(
                            session.probe_for_supporting_evidence,
                            human_probe,
                        ),
                        difference(
                            session.teach_general_rules,
                            human_general_rules,
                        ),
                        difference(
                            session.reinforce_what_was_done_right,
                            human_reinforcement,
                        ),
                        difference(
                            session.correct_mistakes,
                            human_correction,
                        ),
                        difference(
                            session.omp_total,
                            human_total,
                        ),
                        session.model_version,
                        session.prompt_version,
                        to_iso(session.created_at),
                        to_kst_iso(session.created_at),
                        to_iso(rating_created_at),
                        to_kst_iso(rating_created_at),
                        to_iso(rating_updated_at),
                        to_kst_iso(rating_updated_at),
                    ]
                )

        csv_bytes = (
            "\ufeff" + text_buffer.getvalue()
        ).encode("utf-8")

        return StreamingResponse(
            io.BytesIO(csv_bytes),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": (
                    'attachment; filename="research_analysis.csv"'
                )
            },
        )

    except Exception as exc:
        print(
            "=== DEBUG: /api/research-analysis.csv ERROR ===",
            repr(exc),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Research analysis CSV export failed: {exc}",
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
