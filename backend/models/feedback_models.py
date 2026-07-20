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

    transcript, STT segments, 화자 역할 분석, OMP 점수,
    근거 발언, 구조 분석, 코칭 결과를 encounter_id 단위로 저장한다.
    JSON 형태의 자료는 PostgreSQL/SQLite 호환성을 위해
    우선 Text 컬럼에 JSON 문자열로 저장한다.
    """

    __tablename__ = "feedback_session"
    __table_args__ = (
        UniqueConstraint(
            "encounter_id",
            name="uq_feedback_session_encounter_id",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    # 세션 식별자
    encounter_id = Column(
        String(100),
        index=True,
        nullable=False,
    )

    # 연구 대상자 익명 식별자
    supervisor_id = Column(
        String(100),
        index=True,
        nullable=True,
    )
    trainee_id = Column(
        String(100),
        index=True,
        nullable=True,
    )

    # 분석 설정
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
    trainee_level = Column(
        String(50),
        nullable=True,
    )
    language = Column(
        String(20),
        nullable=True,
    )
    audio_ref = Column(
        Text,
        nullable=True,
    )

    # 원자료
    transcript = Column(
        Text,
        nullable=False,
    )
    segments_json = Column(
        Text,
        nullable=True,
    )
    context_json = Column(
        Text,
        nullable=True,
    )

    # 화자 역할 분석
    speaker_mode = Column(
        String(20),
        nullable=False,
        default="auto",
    )
    speaker_mapping_json = Column(
        Text,
        nullable=True,
    )
    speaker_confidence = Column(
        Float,
        nullable=True,
    )
    speaker_confidence_label = Column(
        String(20),
        nullable=True,
    )
    speaker_uncertain = Column(
        Boolean,
        nullable=False,
        default=False,
    )
    speaker_reason = Column(
        Text,
        nullable=True,
    )

    # OMP 5개 microskill 점수
    get_commitment = Column(
        Integer,
        nullable=True,
    )
    probe_for_supporting_evidence = Column(
        Integer,
        nullable=True,
    )
    teach_general_rules = Column(
        Integer,
        nullable=True,
    )
    reinforce_what_was_done_right = Column(
        Integer,
        nullable=True,
    )
    correct_mistakes = Column(
        Integer,
        nullable=True,
    )

    # OMP 요약 점수
    omp_total = Column(
        Integer,
        nullable=True,
    )
    omp_scale = Column(
        Integer,
        nullable=True,
        default=25,
    )
    omp_percent = Column(
        Float,
        nullable=True,
    )

    # 분석 결과 JSON
    evidence_json = Column(
        Text,
        nullable=True,
    )
    structure_json = Column(
        Text,
        nullable=True,
    )
    coach_json = Column(
        Text,
        nullable=True,
    )
    full_result_json = Column(
        Text,
        nullable=True,
    )

    # 재현성과 버전 관리
    model_version = Column(
        String(100),
        nullable=True,
    )
    prompt_version = Column(
        String(100),
        nullable=True,
    )

    # 생성 시각
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )


class CoachEval(Base):
    """
    코칭 리포트가 얼마나 도움이 되었는지(1~5점) 저장하는 테이블.
    """

    __tablename__ = "coach_eval"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    encounter_id = Column(
        String(100),
        index=True,
        nullable=True,
    )
    supervisor_id = Column(
        String(100),
        index=True,
        nullable=True,
    )
    trainee_id = Column(
        String(100),
        index=True,
        nullable=True,
    )

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
    model_version = Column(
        String(100),
        nullable=True,
    )

    helpful_score = Column(
        Integer,
        nullable=False,
    )

    # ["strengths", "improvements_top3"] 같은 리스트를
    # JSON 문자열로 저장
    helpful_flags = Column(
        Text,
        nullable=True,
    )
    comment = Column(
        Text,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )


class CoachMemo(Base):
    """
    '기록' 체크된 코칭 리포트 섹션들을 저장하는 테이블.
    """

    __tablename__ = "coach_memo"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    encounter_id = Column(
        String(100),
        index=True,
        nullable=True,
    )
    supervisor_id = Column(
        String(100),
        index=True,
        nullable=True,
    )
    trainee_id = Column(
        String(100),
        index=True,
        nullable=True,
    )

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
    model_version = Column(
        String(100),
        nullable=True,
    )

    # {"strengths": "...", "script_next_time": "..."}를
    # JSON 문자열로 저장
    saved_sections = Column(
        Text,
        nullable=False,
    )
    note = Column(
        Text,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
