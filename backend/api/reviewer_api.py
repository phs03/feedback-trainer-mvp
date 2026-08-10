# backend/api/reviewer_api.py

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.reviewer_auth import require_reviewer_token
from backend.db import get_db
from backend.models.feedback_models import FeedbackSession, HumanOMPAssessment

router = APIRouter(prefix="/api/reviewer", tags=["reviewer"])


class ReviewerHumanOMPRatingRequest(BaseModel):
    encounter_id: str = Field(..., min_length=1, max_length=100)
    rater_id: str = Field(..., min_length=1, max_length=100)
    get_commitment: int = Field(..., ge=1, le=5)
    probe_for_supporting_evidence: int = Field(..., ge=1, le=5)
    teach_general_rules: int = Field(..., ge=1, le=5)
    reinforce_what_was_done_right: int = Field(..., ge=1, le=5)
    correct_mistakes: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None


def _raw_segments(value: Optional[str]):
    if not value:
        return []
    try:
        data = json.loads(value)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _rating_dict(rating: Optional[HumanOMPAssessment]):
    if rating is None:
        return None

    return {
        "id": rating.id,
        "encounter_id": rating.encounter_id,
        "rater_id": rating.rater_id,
        "get_commitment": rating.get_commitment,
        "probe_for_supporting_evidence": rating.probe_for_supporting_evidence,
        "teach_general_rules": rating.teach_general_rules,
        "reinforce_what_was_done_right": rating.reinforce_what_was_done_right,
        "correct_mistakes": rating.correct_mistakes,
        "omp_total": rating.omp_total,
        "omp_scale": rating.omp_scale,
        "omp_percent": rating.omp_percent,
        "comment": rating.comment,
        "created_at": rating.created_at.isoformat() if getattr(rating, "created_at", None) else None,
        "updated_at": rating.updated_at.isoformat() if getattr(rating, "updated_at", None) else None,
    }


@router.get("/sessions")
def reviewer_sessions(
    rater_id: str = Query(..., min_length=1, max_length=100),
    include_completed: bool = Query(default=False),
    completed_only: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _auth: Dict[str, int] = Depends(require_reviewer_token),
) -> Dict[str, Any]:
    """
    평가자용 세션 목록.

    AI OMP 점수/코칭/evidence/speaker inference는 반환하지 않는다.

    - 기본: 미평가 세션만
    - include_completed=true: 전체 세션
    - completed_only=true: 해당 rater가 평가 완료한 세션만
    """

    rater_id = rater_id.strip()
    if not rater_id:
        raise HTTPException(status_code=422, detail="rater_id is required.")

    all_rows = (
        db.query(FeedbackSession)
        .order_by(FeedbackSession.created_at.asc(), FeedbackSession.id.asc())
        .all()
    )

    ratings = (
        db.query(HumanOMPAssessment)
        .filter(HumanOMPAssessment.rater_id == rater_id)
        .all()
    )
    rating_by_encounter = {
        row.encounter_id: row for row in ratings if row.encounter_id
    }
    rated_encounter_ids = set(rating_by_encounter.keys())

    total_sessions = len(all_rows)
    completed_count = sum(
        1 for row in all_rows if row.encounter_id in rated_encounter_ids
    )
    remaining_count = max(total_sessions - completed_count, 0)

    if completed_only:
        filtered_rows = [
            row for row in all_rows if row.encounter_id in rated_encounter_ids
        ]
    elif include_completed:
        filtered_rows = all_rows
    else:
        filtered_rows = [
            row for row in all_rows if row.encounter_id not in rated_encounter_ids
        ]

    paged_rows = filtered_rows[offset : offset + limit]

    items = []
    for row in paged_rows:
        rating = rating_by_encounter.get(row.encounter_id)
        items.append(
            {
                "feedback_session_id": row.id,
                "encounter_id": row.encounter_id,
                "scenario_code": row.scenario_code,
                "scale_code": row.scale_code,
                "trainee_level": row.trainee_level,
                "language": row.language,
                "transcript": row.transcript,
                "segments": _raw_segments(row.segments_json),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "completed_by_rater": rating is not None,
                "rating": _rating_dict(rating),
            }
        )

    completion_percent = (
        round(completed_count / total_sessions * 100, 1)
        if total_sessions > 0
        else 0.0
    )

    return {
        "status": "ok",
        "rater_id": rater_id,
        "include_completed": include_completed,
        "completed_only": completed_only,
        "total_sessions": total_sessions,
        "completed_count": completed_count,
        "remaining_count": remaining_count,
        "completion_percent": completion_percent,
        "count": len(items),
        "offset": offset,
        "limit": limit,
        "items": items,
    }


@router.post("/human-ratings")
def reviewer_save_human_rating(
    payload: ReviewerHumanOMPRatingRequest,
    db: Session = Depends(get_db),
    _auth: Dict[str, int] = Depends(require_reviewer_token),
) -> Dict[str, Any]:
    session_obj = (
        db.query(FeedbackSession)
        .filter(FeedbackSession.encounter_id == payload.encounter_id)
        .one_or_none()
    )

    if session_obj is None:
        raise HTTPException(status_code=404, detail="Feedback session not found.")

    total = sum(
        [
            payload.get_commitment,
            payload.probe_for_supporting_evidence,
            payload.teach_general_rules,
            payload.reinforce_what_was_done_right,
            payload.correct_mistakes,
        ]
    )
    scale = 25
    percent = round(total / scale * 100, 1)

    rating_obj = (
        db.query(HumanOMPAssessment)
        .filter(
            HumanOMPAssessment.encounter_id == payload.encounter_id,
            HumanOMPAssessment.rater_id == payload.rater_id,
        )
        .one_or_none()
    )

    created = rating_obj is None

    try:
        if rating_obj is None:
            rating_obj = HumanOMPAssessment(
                encounter_id=payload.encounter_id,
                rater_id=payload.rater_id,
                supervisor_id=session_obj.supervisor_id,
                trainee_id=session_obj.trainee_id,
                get_commitment=payload.get_commitment,
                probe_for_supporting_evidence=payload.probe_for_supporting_evidence,
                teach_general_rules=payload.teach_general_rules,
                reinforce_what_was_done_right=payload.reinforce_what_was_done_right,
                correct_mistakes=payload.correct_mistakes,
                omp_total=total,
                omp_scale=scale,
                omp_percent=percent,
                comment=payload.comment,
            )
            db.add(rating_obj)
        else:
            rating_obj.get_commitment = payload.get_commitment
            rating_obj.probe_for_supporting_evidence = payload.probe_for_supporting_evidence
            rating_obj.teach_general_rules = payload.teach_general_rules
            rating_obj.reinforce_what_was_done_right = payload.reinforce_what_was_done_right
            rating_obj.correct_mistakes = payload.correct_mistakes
            rating_obj.omp_total = total
            rating_obj.omp_scale = scale
            rating_obj.omp_percent = percent
            rating_obj.comment = payload.comment

        db.commit()
        db.refresh(rating_obj)

        return {
            "status": "ok",
            "action": "created" if created else "updated",
            "data": _rating_dict(rating_obj),
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Reviewer human rating save failed: {exc}",
        ) from exc
