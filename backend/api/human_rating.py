# backend/api/human_rating.py

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models.feedback_models import (
    FeedbackSession,
    HumanOMPAssessment,
)


router = APIRouter(prefix="/api", tags=["human-rating"])


class HumanOMPRatingRequest(BaseModel):
    encounter_id: str = Field(..., min_length=1, max_length=100)
    rater_id: str = Field(..., min_length=1, max_length=100)

    get_commitment: int = Field(..., ge=1, le=5)
    probe_for_supporting_evidence: int = Field(..., ge=1, le=5)
    teach_general_rules: int = Field(..., ge=1, le=5)
    reinforce_what_was_done_right: int = Field(..., ge=1, le=5)
    correct_mistakes: int = Field(..., ge=1, le=5)

    comment: Optional[str] = None


@router.post("/human-ratings")
def save_human_omp_rating(
    payload: HumanOMPRatingRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    인간 평가자의 OMP 점수를 저장한다.

    동일 encounter_id + rater_id가 이미 있으면 기존 평가를 갱신한다.
    """

    try:
        session_obj = (
            db.query(FeedbackSession)
            .filter(
                FeedbackSession.encounter_id == payload.encounter_id
            )
            .one_or_none()
        )

        if session_obj is None:
            raise HTTPException(
                status_code=404,
                detail="해당 encounter_id의 feedback session이 없습니다.",
            )

        score_values = [
            payload.get_commitment,
            payload.probe_for_supporting_evidence,
            payload.teach_general_rules,
            payload.reinforce_what_was_done_right,
            payload.correct_mistakes,
        ]

        total = sum(score_values)
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

        if rating_obj is None:
            rating_obj = HumanOMPAssessment(
                encounter_id=payload.encounter_id,
                rater_id=payload.rater_id,
                supervisor_id=session_obj.supervisor_id,
                trainee_id=session_obj.trainee_id,
                get_commitment=payload.get_commitment,
                probe_for_supporting_evidence=(
                    payload.probe_for_supporting_evidence
                ),
                teach_general_rules=payload.teach_general_rules,
                reinforce_what_was_done_right=(
                    payload.reinforce_what_was_done_right
                ),
                correct_mistakes=payload.correct_mistakes,
                omp_total=total,
                omp_scale=scale,
                omp_percent=percent,
                comment=payload.comment,
            )
            db.add(rating_obj)
        else:
            rating_obj.get_commitment = payload.get_commitment
            rating_obj.probe_for_supporting_evidence = (
                payload.probe_for_supporting_evidence
            )
            rating_obj.teach_general_rules = (
                payload.teach_general_rules
            )
            rating_obj.reinforce_what_was_done_right = (
                payload.reinforce_what_was_done_right
            )
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
            "data": {
                "id": rating_obj.id,
                "encounter_id": rating_obj.encounter_id,
                "rater_id": rating_obj.rater_id,
                "omp_total": rating_obj.omp_total,
                "omp_scale": rating_obj.omp_scale,
                "omp_percent": rating_obj.omp_percent,
            },
        }

    except HTTPException:
        raise

    except Exception as exc:
        db.rollback()
        print("=== DEBUG: human rating save ERROR ===", repr(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Human OMP rating save failed: {exc}",
        ) from exc


@router.get("/human-ratings")
def get_human_omp_ratings(
    encounter_id: Optional[str] = Query(default=None),
    rater_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    저장된 인간 OMP 평가를 조회한다.
    encounter_id 또는 rater_id로 필터링할 수 있다.
    """

    try:
        query = db.query(HumanOMPAssessment)

        if encounter_id:
            query = query.filter(
                HumanOMPAssessment.encounter_id == encounter_id
            )

        if rater_id:
            query = query.filter(
                HumanOMPAssessment.rater_id == rater_id
            )

        rows = (
            query.order_by(
                HumanOMPAssessment.created_at.desc(),
                HumanOMPAssessment.id.desc(),
            )
            .limit(limit)
            .all()
        )

        items = []

        for row in rows:
            items.append(
                {
                    "id": row.id,
                    "encounter_id": row.encounter_id,
                    "rater_id": row.rater_id,
                    "supervisor_id": row.supervisor_id,
                    "trainee_id": row.trainee_id,
                    "get_commitment": row.get_commitment,
                    "probe_for_supporting_evidence": (
                        row.probe_for_supporting_evidence
                    ),
                    "teach_general_rules": row.teach_general_rules,
                    "reinforce_what_was_done_right": (
                        row.reinforce_what_was_done_right
                    ),
                    "correct_mistakes": row.correct_mistakes,
                    "omp_total": row.omp_total,
                    "omp_scale": row.omp_scale,
                    "omp_percent": row.omp_percent,
                    "comment": row.comment,
                    "created_at": (
                        row.created_at.isoformat()
                        if row.created_at
                        else None
                    ),
                    "updated_at": (
                        row.updated_at.isoformat()
                        if row.updated_at
                        else None
                    ),
                }
            )

        return {
            "status": "ok",
            "count": len(items),
            "items": items,
        }

    except Exception as exc:
        print("=== DEBUG: human rating query ERROR ===", repr(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Human OMP rating query failed: {exc}",
        ) from exc
