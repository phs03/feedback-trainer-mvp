# backend/main.py

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.db import Base, engine
import backend.models  # ✅ DbHealthCheck 포함 모델들 로딩

from backend.api.stt import router as stt_router, client as stt_client
from backend.api.feedback import router as feedback_router
from backend.api.report import router as report_router
from backend.api.db_test import router as db_debug_router  # ✅ 디버그 라우터

app = FastAPI(title="AI Feedback MVP", version="0.1.0")

# CORS는 지금처럼 * 로 풀어둔 상태 유지해도 OK
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("=== CORS ALLOW_ORIGINS === * (all origins allowed)")


class HealthResponse(BaseModel):
    status: str
    version: str


@app.on_event("startup")
def on_startup():
    # ✅ 서버 시작 시 DB 테이블 생성
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


# --- 기능별 라우터 연결 ---
app.include_router(stt_router)
app.include_router(feedback_router)
app.include_router(report_router)
app.include_router(db_debug_router)  # ✅ debug 라우터까지 연결
