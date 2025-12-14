# backend/models/health_check.py

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime

from backend.db import Base


class DbHealthCheck(Base):
    """
    DB 연결 및 마이그레이션 상태를 간단히 확인하기 위한 헬스 체크용 테이블.

    - 최소 1개의 row만 있어도 DB 연결/쓰기/읽기가 되는지 확인할 수 있음.
    - 특별한 비즈니스 로직은 없고, db_test 라우터 등에서 사용 가능.
    """

    __tablename__ = "db_health_check"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    # 예: "init", "test", "seed" 같은 단어를 저장해 둘 수 있음
    name = Column(String(50), nullable=False, default="health_check")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<DbHealthCheck id={self.id} name={self.name!r} created_at={self.created_at}>"
