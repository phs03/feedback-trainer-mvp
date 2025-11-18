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

        # 🔥 STT + Speaker Diarization 호출
        #
        # - diarization 지원 모델(예: gpt-4o 기반 STT)에 따라 model/response_format은
        #   나중에 바뀔 수 있으니, 실제 응답 구조는 한 번 print 찍어서 확인해 보는 게 좋다.
        #
        # 여기서는 'diarized_json' 형태로
        # { text, language, segments[] }를 돌려준다고 가정한다.
        resp = client.audio.transcriptions.create(
            # diarization + transcription 지원 모델명 (OpenAI 최신 문서 참고)
            model="gpt-4o-transcribe-diarize",
            file=audio_buffer,
            # 화자 구분이 포함된 JSON 포맷 요청
            response_format="diarized_json",
            # 한국어 위주라면 명시해 두는 것이 인식에 도움 될 수 있음
            language="ko",
        )

        # resp는 일반적으로 dict 비슷한 구조일 것이라 가정:
        # {
        #   "text": "...",
        #   "language": "ko",
        #   "segments": [
        #       {"speaker": "SPEAKER_00", "start": ..., "end": ..., "text": "..."},
        #       ...
        #   ]
        # }
        #
        # 혹시 resp가 pydantic 객체 등이라면, dict()로 변환이 필요할 수 있다.
        # (SDK 버전에 따라 달라질 수 있음)
        if hasattr(resp, "to_dict"):
            data = resp.to_dict()
        elif isinstance(resp, dict):
            data = resp
        else:
            # text, language, segments 속성을 직접 꺼내서 구성
            data = {
                "text": getattr(resp, "text", None),
                "language": getattr(resp, "language", N
