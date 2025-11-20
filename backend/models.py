# backend/models.py

from sqlalchemy import Column, Integer, String, DateTime, func
from backend.db import Base


class DbHealthCheck(Base):
    """
    DB 연결 테스트용 간단한 테이블
    /debug/db-test 엔드포인트에서 한 줄 INSERT해서 확인한다.
    """
    __tablename__ = "db_health_check"

    id = Column(Integer, primary_key=True, index=True)
    note = Column(String(255), nullable=False, default="ok")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
