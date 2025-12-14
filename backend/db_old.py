# backend/db.py

import os
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# 프로젝트 루트 기준으로 SQLite 파일 생성 (기본값)
ROOT_DIR = Path(__file__).resolve().parents[2]
default_sqlite_url = f"sqlite:///{ROOT_DIR / 'feedback.db'}"

# DATABASE_URL 환경변수가 있으면 그걸 쓰고, 아니면 SQLite 기본값
DATABASE_URL = os.getenv("DATABASE_URL", default_sqlite_url)

# echo=True 로 두면 SQL 로그가 찍힘 (개발 단계에서는 유용)
engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency에서 쓸 세션 제공 함수.
    예:
      def some_endpoint(db: Session = Depends(get_db)):
          ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
