# backend/models/scale_models.py

from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    ForeignKey,
    DateTime,
)
from sqlalchemy.orm import relationship

from backend.db import Base


class Scenario(Base):
    """
    피드백이 발생하는 '상황' 정의
    예: EM_DEBRIEF(시뮬레이션 디브리핑), CLINICAL_OMP(임상 OMP 피드백) 등
    """
    __tablename__ = "scenario"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)

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

    # 관계
    scales = relationship("Scale", back_populates="scenario")


class Scale(Base):
    """
    특정 상황에서 사용하는 스케일 정의
    예: OSAD_DEBRIEFER, OMP_CLINICAL 등
    """
    __tablename__ = "scale"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # 어떤 Scenario에 속하는지
    scenario_id = Column(Integer, ForeignKey("scenario.id"), nullable=False)

    # 스코어 관련 메타 정보
    max_item_score = Column(Integer, nullable=False, default=5)
    num_items = Column(Integer, nullable=False, default=0)
    max_total = Column(Integer, nullable=False, default=0)

    version = Column(String(50), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

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

    # 관계
    scenario = relationship("Scenario", back_populates="scales")
    items = relationship("ScaleItem", back_populates="scale")


class ScaleItem(Base):
    """
    스케일의 개별 문항 정의
    예: OSAD의 approach, learning_env ...
        OMP의 Get a commitment, Probe for evidence ...
    """
    __tablename__ = "scale_item"

    id = Column(Integer, primary_key=True, index=True)
    scale_id = Column(Integer, ForeignKey("scale.id"), nullable=False)

    # 스케일 내에서의 코드 / 순서
    item_code = Column(String(50), nullable=False)
    order_index = Column(Integer, nullable=False, default=0)

    # 문항 제목 (한글/영어)
    title_ko = Column(String(255), nullable=False)
    title_en = Column(String(255), nullable=False)

    # 필요하면 길게 설명
    description_ko = Column(Text, nullable=True)
    description_en = Column(Text, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)

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

    # 관계
    scale = relationship("Scale", back_populates="items")
