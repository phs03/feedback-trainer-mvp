# backend/db.py

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ── 1) .env 로드 ──────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parents[1]  # ai_feedback_mvp
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
    print("=== DEBUG[db]: .env 로드됨 ===", ENV_PATH)
else:
    print("=== DEBUG[db]: .env 파일을 찾지 못함 ===", ENV_PATH)

# ── 2) DATABASE_URL 읽기 ─────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # 꼭 Postgres만 쓰고 싶으면 RuntimeError로 바꿔도 됨
    raise RuntimeError("DATABASE_URL 환경변수가 설정되어 있지 않습니다.")

print("=== DEBUG[db]: USING DATABASE_URL ===", DATABASE_URL)

# ── 3) SQLAlchemy 기본 설정 ──────────────────────────
engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── 4) 의존성 주입용 세션 함수 ───────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
