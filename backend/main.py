# backend/main.py

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
    앱 시작 시 SQLAlchemy 모델(backend.models)을 기준으로
    연결된 DB에 테이블을 생성/확인한다.
    """
    print("=== DB 테이블 생성/확인 시작 ===")
    Base.metadata.create_all(bind=engine)
    print("=== DB 테이블 생성/확인 완료 ===")


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


@app.get("/healthz", response_model=HealthResponse)
def healthz():
    return HealthResponse(status="alive", version="0.1.0")


@app.get("/readyz", response_model=HealthResponse)
def readyz():
    return HealthResponse(status="ready", version="0.1.0")


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
