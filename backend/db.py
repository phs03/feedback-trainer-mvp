# backend/db.py

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 1) DATABASE_URL 읽기
#    - Render / 로컬 둘 다 여기서 통일
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # 로컬 개발 기본값: SQLite 파일
    print("⚠ DATABASE_URL not found — fallback to SQLite")
    DATABASE_URL = "sqlite:///./feedback.db"

print("=== DEBUG[db]: USING DATABASE_URL ===", DATABASE_URL)

# 2) 엔진 생성
#    - SQLite일 때만 check_same_thread 옵션 필요
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
)

# 3) 세션 / Base
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)
Base = declarative_base()
