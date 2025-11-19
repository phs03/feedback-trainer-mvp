# backend/api/stt.py

import os
import io
import json
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
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
      ],
      "transcript": "전체 대화 한 줄 텍스트..."
    }
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
        # 업로드된 바이너리를 메모리 버퍼로 변환
        audio_bytes = await file.read()
        audio_buffer = io.BytesIO(audio_bytes)
        audio_buffer.name = file.filename or "recording.webm"

        print("=== DEBUG: STT 호출 시작 ===")
        # 🔥 STT + Speaker Diarization 호출
        resp = client.audio.transcriptions.create(
            # diarization + transcription 지원 모델명
            model="gpt-4o-transcribe-diarize",
            file=audio_buffer,
            # diarized_json: text + segments(speaker, start, end, text)
            response_format="diarized_json",
            language="ko",
        )

        # 여기서 resp가 어떤 타입인지 로그로 한번 확인
        print("=== DEBUG: STT raw resp type ===", type(resp))

        # ▣ resp를 dict로 변환
        if isinstance(resp, dict):
            data = resp
        elif hasattr(resp, "model_dump"):
            data = resp.model_dump()
        elif hasattr(resp, "to_dict"):
            data = resp.to_dict()
        elif isinstance(resp, str):
            # 혹시 문자열 JSON이라면
            try:
                data = json.loads(resp)
            except Exception:
                data = {"raw": resp}
        else:
            # 마지막 fallback: 가능한 속성만 추출
            data = {
                "text": getattr(resp, "text", None),
                "language": getattr(resp, "language", None),
                "segments": getattr(resp, "segments", None),
            }

        print("=== DEBUG: STT data ===", data)

        text = data.get("text")
        language = data.get("language")
        segments = data.get("segments") or []

        result = {
            "text": text,
            "language": language,
            "segments": segments,
            # ✅ 기존 프론트에서 쓰던 필드와 호환
            "transcript": text,
        }

        print("=== DEBUG: STT result to client ===", result)

        # ⚠ 여기서 None을 리턴하면 프론트에서 null이 보이므로
        # 항상 dict를 그대로 리턴 (FastAPI가 JSON으로 직렬화)
        return result

    except Exception as e:
        print("=== DEBUG: STT ERROR ===", repr(e))
        raise HTTPException(status_code=500, detail=f"STT failed: {e}")
