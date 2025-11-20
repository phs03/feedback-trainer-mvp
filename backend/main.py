# backend/main.py

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 🔹 DB 관련
from backend.db import Base, engine
import backend.models  # DbHealthCheck 포함

# 🔹 API 라우터들
from backend.api.stt import router as stt_router, client as stt_client
from backend.api.feedback import router as feedback_router
from backend.api.report import router as report_router
from backend.api.db_test import router as db_debug_router  # ✅ 디버그 라우터

app = FastAPI(title="AI Feedback MVP", version="0.1.0")

# =========================
# CORS 설정
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


# ✅ 서버 시작 시 DB 테이블 생성
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    print("=== DB 테이블 생성/확인 완료 ===")


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


# 🔹 OpenAI API 키 / 클라이언트 테스트용 엔드포인트
@app.get("/test-key")
def test_key():
    try:
        models = stt_client.models.list()
        first_model = models.data[0].id if models.data else None
        return {"ok": True, "example_model": first_model}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# --- 기능별 라우터 연결 ---
app.include_router(stt_router)
app.include_router(feedback_router)
app.include_router(report_router)
app.include_router(db_debug_router)  # ✅ DB 디버그 라우터
