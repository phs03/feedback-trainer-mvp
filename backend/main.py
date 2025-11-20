# backend/main.py

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 🔹 STT 라우터 + OpenAI client 같이 가져오기
from backend.api.stt import router as stt_router, client as stt_client
from backend.api.feedback import router as feedback_router
from backend.api.report import router as report_router

app = FastAPI(title="AI Feedback MVP", version="0.1.0")

# =========================
# CORS 설정
# =========================

# Render / 로컬 공통으로 쓸 origin 목록 기본값
default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://feedback-trainer-mvp.vercel.app",
]

# ALLOWED_ORIGINS 환경변수에서 가져오기
# 예: "https://feedback-trainer-mvp.vercel.app,http://localhost:5173"
env_origins = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]

if env_origins:
    origins = env_origins
else:
    origins = default_origins

# 지금은 그냥 모두 허용해도 되면 아래처럼 * 로 풀어도 됨
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 필요하면 origins 로 바꿔도 됨
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


# 루트 엔드포인트
@app.get("/", response_model=HealthResponse)
def root():
    return HealthResponse(
        status="AI Feedback MVP Server Running",
        version="0.1.0",
    )


# 헬스 엔드포인트
@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", version="0.1.0")


@app.get("/healthz", response_model=HealthResponse)
def healthz():
    """
    Liveness Probe: 서버 프로세스가 살아 있는지 확인
    """
    return HealthResponse(status="alive", version="0.1.0")


@app.get("/readyz", response_model=HealthResponse)
def readyz():
    """
    Readiness Probe: 서버가 요청을 처리할 준비가 되었는지 확인
    - 나중에 DB 연결, 모델 로딩 상태 등을 여기에 추가
    """
    return HealthResponse(status="ready", version="0.1.0")


# 🔹 OpenAI API 키 / 클라이언트 테스트용 엔드포인트
@app.get("/test-key")
def test_key():
    """
    STT 모듈에서 사용하는 OpenAI client(stt_client)가
    실제로 모델 리스트를 가져올 수 있는지 확인하기 위한 엔드포인트.
    """
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
