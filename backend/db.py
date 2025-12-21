# backend/db.py

import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

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
    raise RuntimeError("DATABASE_URL 환경변수가 설정되어 있지 않습니다.")

# ── 2-1) URL 정규화 (Render/SQLAlchemy 호환 + SSL 보강) ──
def normalize_database_url(raw_url: str) -> str:
    """
    - 'postgres://' 스킴을 SQLAlchemy 표준 'postgresql://'로 변환
    - sslmode 파라미터가 없으면 sslmode=require를 보강 (특히 External DB URL 대응)
    """
    url = raw_url.strip()

    # SQLAlchemy는 'postgresql://' 권장
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    # URL 파싱 후 query 보강
    try:
        p = urlparse(url)
        q = dict(parse_qsl(p.query, keep_blank_values=True))

        # 이미 sslmode가 있으면 유지, 없으면 require로 보강
        if "sslmode" not in q:
            q["sslmode"] = "require"

        new_query = urlencode(q, doseq=True)
        p2 = p._replace(query=new_query)
        return urlunparse(p2)
    except Exception:
        # 파싱 실패 시 원문 반환(그래도 create_engine에서 에러가 명확히 뜸)
        return url

def mask_db_url_for_log(url: str) -> str:
    """로그에 비밀번호가 노출되지 않도록 마스킹"""
    try:
        p = urlparse(url)
        netloc = p.netloc
        if "@" in netloc and ":" in netloc.split("@")[0]:
            userinfo, hostinfo = netloc.split("@", 1)
            user = userinfo.split(":", 1)[0]
            netloc = f"{user}:***@{hostinfo}"
        p2 = p._replace(netloc=netloc)
        return urlunparse(p2)
    except Exception:
        return "***"

DATABASE_URL = normalize_database_url(DATABASE_URL)

print("=== DEBUG[db]: USING DATABASE_URL (masked) ===", mask_db_url_for_log(DATABASE_URL))

# ── 3) SQLAlchemy 기본 설정 ──────────────────────────
# pool_pre_ping: 죽은 커넥션 자동 감지(배포 환경에서 유용)
engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ── 4) 의존성 주입용 세션 함수 ───────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
