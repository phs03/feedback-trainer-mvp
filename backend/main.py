# backend/main.py

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import time

# 🔹 DB 관련
from backend.db import Base, engine
import backend.models  # DbHealthCheck, CoachEval, CoachMemo 등 전체 모델 import

# 🔹 API 라우터들
from backend.api.stt import router as stt_router, client as stt_client
from backend.api.feedback import router as feedback_router
from backend.api.report import router as report_router
from backend.api.db_test import router as db_debug_router
from backend.api import coach_eval
from backend.api.db_admin import router as db_admin_router  # ★ DB admin 라우터

app = FastAPI(
    title="AI Feedback MVP",
    version="0.1.0",
    description="지도전문의·전공의 피드백 대화 STT + OSAD/OMP 분석용 MVP 백엔드",
)

# =========================
# CORS 설정
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # 배포 시에는 특정 도메인으로 제한 권장
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("=== CORS ALLOW_ORIGINS === * (all origins allowed)")
# =========================
# 런타임 상태 플래그 (Render 진단용)
# =========================
APP_STARTED_AT = time.time()
DB_READY = False
DB_LAST_ERROR = None


# =========================
# 헬스 체크용 스키마
# =========================
class HealthResponse(BaseModel):
    status: str
    version: str


# =========================
# 서버 시작 시 DB 테이블 생성
# =========================
@app.on_event("startup")
def on_startup():
    """
    배포 환경(Render)에서는 DB 연결 문제가 있을 수 있으므로,
    startup에서 DB 실패가 앱 전체 기동 실패로 이어지지 않게 한다.
    - healthz: 앱 프로세스 생존 여부 (DB 무관)
    - readyz: DB까지 포함한 준비 상태
    """
    global DB_READY, DB_LAST_ERROR

    print("=== STARTUP: 앱 기동 시작 ===")
    DB_READY = False
    DB_LAST_ERROR = None

    # 1) DB 연결 체크 (짧게)
    try:
        print("=== STARTUP: DB 연결 체크 시작 ===")
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("=== STARTUP: DB 연결 체크 OK ===")
    except SQLAlchemyError as e:
        DB_LAST_ERROR = f"DB connect failed: {e}"
        print(f"=== STARTUP: DB 연결 실패 === {DB_LAST_ERROR}")
        # DB가 안 돼도 앱은 떠야 하므로 return 하지 않고 계속 진행
        return
    except Exception as e:
        DB_LAST_ERROR = f"Unexpected DB error: {e}"
        print(f"=== STARTUP: DB 예외 === {DB_LAST_ERROR}")
        return

    # 2) 테이블 생성/확인 (DB가 되는 경우에만)
    try:
        print("=== STARTUP: DB 테이블 생성/확인 시작 ===")
        Base.metadata.create_all(bind=engine)
        DB_READY = True
        print("=== STARTUP: DB 테이블 생성/확인 완료 (DB_READY=True) ===")
    except SQLAlchemyError as e:
        DB_LAST_ERROR = f"DB create_all failed: {e}"
        DB_READY = False
        print(f"=== STARTUP: DB 테이블 생성 실패 === {DB_LAST_ERROR}")
    except Exception as e:
        DB_LAST_ERROR = f"Unexpected create_all error: {e}"
        DB_READY = False
        print(f"=== STARTUP: create_all 예외 === {DB_LAST_ERROR}")



# =========================
# 기본 헬스 체크 엔드포인트
# =========================
@app.get("/", response_model=HealthResponse)
def root():
    return HealthResponse(
        status="AI Feedback MVP Server Running",
        version="0.1.0",
    )


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", version="0.1.0")



@app.get("/healthz")
def healthz():
    # DB와 무관하게 프로세스가 떠 있으면 OK
    uptime_sec = int(time.time() - APP_STARTED_AT)
    return {"status": "alive", "uptime_sec": uptime_sec, "version": "0.1.0"}



@app.get("/readyz")
def readyz():
    # DB까지 준비되면 ready
    if DB_READY:
        return {"status": "ready", "db": "ok", "version": "0.1.0"}

    # DB가 아직 준비 안 된 경우, 원인 노출(배포 진단용)
    return {
        "status": "not_ready",
        "db": "not_ready",
        "error": DB_LAST_ERROR,
        "version": "0.1.0",
    }



# =========================
# OpenAI API 테스트
# =========================
@app.get("/test-key")
def test_key():
    """
    STT에서 사용하는 OpenAI client(stt_client)가
    정상적으로 동작하는지 간단히 확인하는 엔드포인트.
    """
    try:
        models = stt_client.models.list()
        first_model = models.data[0].id if models.data else None
        return {"ok": True, "example_model": first_model}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# =========================
# API 라우터 등록
# =========================
# STT + 화자 분리
app.include_router(stt_router)

# 피드백 분석(OSAD/OMP 등) + 코칭 리포트
app.include_router(feedback_router)

# 코칭 리포트 평가/메모 집계를 위한 추가 라우터 (report)
app.include_router(report_router)

# coach_eval용 예전 라우터(호환 목적)
app.include_router(coach_eval.router)

# DB 디버그용 (/db/info, /db/tables 등)
app.include_router(db_debug_router)

# DB admin용 (/db/admin/...) - 로우 카운트, truncate 등
app.include_router(db_admin_router)
