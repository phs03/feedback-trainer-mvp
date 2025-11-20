# backend/models.py

from sqlalchemy import Column, Integer, String, DateTime, func
from backend.db import Base


class DbHealthCheck(Base):
    __tablename__ = "db_health_check"

    id = Column(Integer, primary_key=True, index=True)
    note = Column(String(255), nullable=False, default="ok")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
