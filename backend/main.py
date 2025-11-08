import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="AI Feedback MVP", version="0.1.0")

# ALLOWED_ORIGINS = "https://your-frontend.vercel.app,https://staging.example.com"
origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if not origins:
    # 초기에는 임시로 * 허용 → Vercel 도메인 확정 후 반드시 좁히기!
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class HealthResponse(BaseModel):
    status: str
    version: str

@app.get("/", response_model=HealthResponse)
def root():
    return HealthResponse(status="AI Feedback MVP Server Running", version="0.1.0")

@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", version="0.1.0")

from backend.api.stt import router as stt_router
from backend.api.feedback import router as feedback_router
from backend.api.report import router as report_router

app.include_router(stt_router)
app.include_router(feedback_router)
app.include_router(report_router)