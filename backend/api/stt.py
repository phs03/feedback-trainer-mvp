# backend/api/stt.py

import os
import io
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from openai import OpenAI

# ----------------------------------------------------
# 1) 프로젝트 루트(ai_feedback_mvp/.env)에서 .env 로드
#    stt.py 위치: ai_feedback_mvp/backend/api/stt.py
#    parents[2] => ai_feedback_mvp
# ----------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[2]   # .../ai_feedback_mvp
ENV_PATH = ROOT_DIR / ".env"

print("=== DEBUG: ROOT_DIR ===", ROOT_DIR)
print("=== DEBUG: ENV PATH ===", ENV_PATH)

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
    print("=== DEBUG: .env 로드됨 ===")
else:
    print("=== DEBUG: .env 파일이 존재하지 않음 ===")

api_key = os.getenv("OPENAI_API_KEY")
print(
    "=== DEBUG: LOADED API KEY (first 10 chars) ===",
    api_key[:10] if api_key else "None",
)

if not api_key:
    raise RuntimeError("OPENAI_API_KEY not found after loading .env!")

# OpenAI 클라이언트 (main.py에서 stt_client로도 쓰기 위해 export)
client = OpenAI(api_key=api_key)

# FastAPI 라우터
router = APIRouter(prefix="/api", tags=["stt"])


@router.post("/stt")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    음성 파일을 Whisper STT로 변환하는 엔드포인트
    - 프론트에서는 FormData의 필드 이름을 "file"로 보냄
    """
    if not file or not file.content_type:
        raise HTTPException(
            status_code=400,
            detail="audio file required (field name: 'file')",
        )

    if not file.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=400,
            detail=f"audio file required, got {file.content_type!r}",
        )

    try:
        audio_bytes = await file.read()
        audio_buffer = io.BytesIO(audio_bytes)
        audio_buffer.name = file.filename or "recording.webm"

        # 🔥 Whisper STT 호출
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_buffer,
            language="ko",
        )

        text = getattr(resp, "text", None)
        return JSONResponse({"transcript": text})

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT failed: {e}")
