# backend/models/feedback_models.py

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from backend.db import Base


class FeedbackSession(Base):
    """
    한 번의 OMP 피드백 분석 세션 전체를 저장하는 테이블.
    """

    __tablename__ = "feedback_session"
    __table_args__ = (
        UniqueConstraint(
            "encounter_id",
            name="uq_feedback_session_encounter_id",
        ),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    encounter_id = Column(String(100), index=True, nullable=False)

    supervisor_id = Column(String(100), index=True, nullable=True)
    trainee_id = Column(String(100), index=True, nullable=True)

    scenario_code = Column(
        String(50),
        nullable=False,
        default="CLINICAL_OMP",
    )
    scale_code = Column(
        String(50),
        nullable=False,
        default="OMP_CORE_FIVE",
    )
    trainee_level = Column(String(50), nullable=True)
    language = Column(String(20), nullable=True)
    audio_ref = Column(Text, nullable=True)

    transcript = Column(Text, nullable=False)
    segments_json = Column(Text, nullable=True)
    context_json = Column(Text, nullable=True)

    speaker_mode = Column(
        String(20),
        nullable=False,
        default="auto",
    )
    speaker_mapping_json = Column(Text, nullable=True)
    speaker_confidence = Column(Float, nullable=True)
    speaker_confidence_label = Column(String(20), nullable=True)
    speaker_uncertain = Column(
        Boolean,
        nullable=False,
        default=False,
    )
    speaker_reason = Column(Text, nullable=True)

    get_commitment = Column(Integer, nullable=True)
    probe_for_supporting_evidence = Column(Integer, nullable=True)
    teach_general_rules = Column(Integer, nullable=True)
    reinforce_what_was_done_right = Column(Integer, nullable=True)
    correct_mistakes = Column(Integer, nullable=True)

    omp_total = Column(Integer, nullable=True)
    omp_scale = Column(Integer, nullable=True, default=25)
    omp_percent = Column(Float, nullable=True)

    evidence_json = Column(Text, nullable=True)
    structure_json = Column(Text, nullable=True)
    coach_json = Column(Text, nullable=True)
    full_result_json = Column(Text, nullable=True)

    model_version = Column(String(100), nullable=True)
    prompt_version = Column(String(100), nullable=True)

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )


class HumanOMPAssessment(Base):
    """
    인간 평가자가 한 피드백 세션에 부여한 OMP 평가 점수.

    encounter_id와 rater_id의 조합은 유일하다.
    동일 평가자가 동일 세션을 다시 저장하면 API에서 기존 행을 갱신한다.
    """

    __tablename__ = "human_omp_assessment"
    __table_args__ = (
        UniqueConstraint(
            "encounter_id",
            "rater_id",
            name="uq_human_omp_encounter_rater",
        ),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    encounter_id = Column(String(100), index=True, nullable=False)
    rater_id = Column(String(100), index=True, nullable=False)

    supervisor_id = Column(String(100), index=True, nullable=True)
    trainee_id = Column(String(100), index=True, nullable=True)

    get_commitment = Column(Integer, nullable=False)
    probe_for_supporting_evidence = Column(Integer, nullable=False)
    teach_general_rules = Column(Integer, nullable=False)
    reinforce_what_was_done_right = Column(Integer, nullable=False)
    correct_mistakes = Column(Integer, nullable=False)

    omp_total = Column(Integer, nullable=False)
    omp_scale = Column(Integer, nullable=False, default=25)
    omp_percent = Column(Float, nullable=False)

    comment = Column(Text, nullable=True)

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class CoachEval(Base):
    """
    코칭 리포트가 얼마나 도움이 되었는지 저장하는 테이블.
    """

    __tablename__ = "coach_eval"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    encounter_id = Column(String(100), index=True, nullable=True)
    supervisor_id = Column(String(100), index=True, nullable=True)
    trainee_id = Column(String(100), index=True, nullable=True)

    scenario_code = Column(
        String(50),
        nullable=False,
        default="CLINICAL_OMP",
    )
    scale_code = Column(
        String(50),
        nullable=False,
        default="OMP_CORE_FIVE",
    )
    model_version = Column(String(100), nullable=True)

    helpful_score = Column(Integer, nullable=False)
    helpful_flags = Column(Text, nullable=True)
    comment = Column(Text, nullable=True)

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )


class CoachMemo(Base):
    """
    사용자가 '기록' 체크한 코칭 리포트 섹션을 저장하는 테이블.
    """

    __tablename__ = "coach_memo"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    encounter_id = Column(String(100), index=True, nullable=True)
    supervisor_id = Column(String(100), index=True, nullable=True)
    trainee_id = Column(String(100), index=True, nullable=True)

    scenario_code = Column(
        String(50),
        nullable=False,
        default="CLINICAL_OMP",
    )
    scale_code = Column(
        String(50),
        nullable=False,
        default="OMP_CORE_FIVE",
    )
    model_version = Column(String(100), nullable=True)

    saved_sections = Column(Text, nullable=False)
    note = Column(Text, nullable=True)

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
