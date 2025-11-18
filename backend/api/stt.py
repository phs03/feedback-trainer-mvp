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

# OpenAI 클라이언트
client = OpenAI(api_key=api_key)

# FastAPI 라우터
router = APIRouter(prefix="/api", tags=["stt"])


@router.post("/stt")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    음성 파일을 STT + Speaker Diarization까지 수행하는 엔드포인트

    🔹 요청
      - FormData: { file: <audio> }
      - content_type: audio/* (webm, wav 등)

    🔹 응답 예시(JSON)
    {
      "text": "전체 대화 한 줄 텍스트...",
      "language": "ko",
      "segments": [
        {
          "speaker": "SPEAKER_00",
          "start": 0.0,
          "end": 4.2,
          "text": "먼저 너 생각은 어땠어?"
        },
        {
          "speaker": "SPEAKER_01",
          "start": 4.3,
          "end": 10.1,
          "text": "저는 환자 상태를 안정적이라고 판단했습니다."
        }
      ]
    }

    ⚠️ 프론트엔드에서는 기존 transcript 대신 text/segments를 사용하도록 수정 필요.
       (당장은 transcript 호환용 필드도 같이 내려줌)
    """
    if not file or not file.content_type:
        rai
