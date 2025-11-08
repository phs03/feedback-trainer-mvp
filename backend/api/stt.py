# backend/api/stt.py
import os
import io
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from openai import OpenAI

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_PATH)

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    # 문제 원인 파악용: 경로와 None 여부를 에러로 명확히
    raise RuntimeError(f"OPENAI_API_KEY not found. Expected at: {ENV_PATH}")

client = OpenAI(api_key=api_key)

router = APIRouter(prefix="/api", tags=["stt"])

@router.post("/stt")
async def transcribe_audio(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail=f"audio file required, got {file.content_type!r}")

    try:
        audio_bytes = await file.read()
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = file.filename or "recording.webm"

        # OpenAI Whisper API 호출
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="ko",  # 한국어만 처리할 때 주석 해제
        )
        text = getattr(resp, "text", str(resp))
        return JSONResponse({"text": text})

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT failed: {e}")
