# backend/models/feedback_models.py

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
)
from backend.db import Base


class CoachEval(Base):
    """
    코칭 리포트가 얼마나 도움이 되었는지(1~5점) 저장하는 테이블
    """

    __tablename__ = "coach_eval"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    encounter_id = Column(String(100), index=True, nullable=True)
    supervisor_id = Column(String(100), index=True, nullable=True)
    trainee_id = Column(String(100), index=True, nullable=True)

    scenario_code = Column(String(50), nullable=False, default="EM_DEBRIEF")
    scale_code = Column(String(50), nullable=False, default="OSAD_DEBRIEFER")
    model_version = Column(String(100), nullable=True)

    helpful_score = Column(Integer, nullable=False)  # 1~5
    # ["strengths", "improvements_top3"] 같은 리스트를 JSON 문자열로 저장
    helpful_flags = Column(Text, nullable=True)
    comment = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CoachMemo(Base):
    """
    '기록' 체크된 코칭 리포트 섹션들을 저장하는 테이블
    """

    __tablename__ = "coach_memo"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    encounter_id = Column(String(100), index=True, nullable=True)
    supervisor_id = Column(String(100), index=True, nullable=True)
    trainee_id = Column(String(100), index=True, nullable=True)

    scenario_code = Column(String(50), nullable=False, default="EM_DEBRIEF")
    scale_code = Column(String(50), nullable=False, default="OSAD_DEBRIEFER")
    model_version = Column(String(100), nullable=True)

    # {"strengths": "...", "script_next_time": "..."} 를 JSON 문자열로 저장
    saved_sections = Column(Text, nullable=False)
    note = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
