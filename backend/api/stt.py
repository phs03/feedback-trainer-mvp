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
#    - 로컬 개발: .env에서 OPENAI_API_KEY 읽기
#    - Render 배포: .env가 없어도, 환경변수에 설정된 값 사용
# ----------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[2]  # .../ai_feedback_mvp
ENV_PATH = ROOT_DIR / ".env"

print("=== DEBUG[stt]: ROOT_DIR ===", ROOT_DIR)
print("=== DEBUG[stt]: ENV PATH ===", ENV_PATH)

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
    print("=== DEBUG[stt]: .env 로드됨 ===")
else:
    print("=== DEBUG[stt]: .env 파일이 존재하지 않음 (환경변수만 사용) ===")

# ----------------------------------------------------
# 2) OPENAI_API_KEY 읽기
#    - 로컬: .env 또는 OS 환경변수
#    - Render: Render Environment에 넣어둔 값
# ----------------------------------------------------
api_key = os.getenv("OPENAI_API_KEY")
print(
    "=== DEBUG[stt]: LOADED API KEY (first 10 chars) ===",
    api_key[:10] if api_key else "None",
)

if not api_key:
    # 여기서 바로 죽도록 해서, 잘못된 설정을 빨리 발견할 수 있게 함
    raise RuntimeError("OPENAI_API_KEY not found after loading .env / env vars!")

# ----------------------------------------------------
# 3) OpenAI 클라이언트 생성
# ----------------------------------------------------
client = OpenAI(api_key=api_key)

# ----------------------------------------------------
# 4) FastAPI 라우터
# ----------------------------------------------------
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
    # -------------------------
    # 1) 요청 검증
    # -------------------------
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
        # -------------------------
        # 2) 업로드된 바이너리를 메모리 버퍼로 변환
        # -------------------------
        audio_bytes = await file.read()
        audio_buffer = io.BytesIO(audio_bytes)
        audio_buffer.name = file.filename or "recording.webm"

        print("=== DEBUG[stt]: STT 호출 시작 ===")

        # -------------------------
        # 3) STT + Speaker Diarization 호출
        #    - 언어는 자동 감지 (language 파라미터 미지정)
        #    - diarized_json 형식으로 받아 text + segments 동시 리턴
        # -------------------------
        resp = client.audio.transcriptions.create(
            model="gpt-4o-transcribe-diarize",
            file=audio_buffer,
            response_format="diarized_json",
        )

        print("=== DEBUG[stt]: STT raw resp type ===", type(resp))

        # -------------------------
        # 4) 응답 객체를 dict로 변환 (여러 경우에 대비)
        # -------------------------
        if isinstance(resp, dict):
            data = resp
        elif hasattr(resp, "model_dump"):
            # pydantic 기반 객체일 경우
            data = resp.model_dump()
        elif hasattr(resp, "to_dict"):
            data = resp.to_dict()
        elif isinstance(resp, str):
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

        print("=== DEBUG[stt]: STT data ===", data)

        # -------------------------
        # 5) 최종 응답 스키마 정리
        # -------------------------
        text = data.get("text")
        language = data.get("language")
        segments = data.get("segments") or []

        result = {
            "text": text,
            "language": language,
            "segments": segments,
            # ✅ 프론트에서 사용하는 필드 이름과 호환
            "transcript": text,
        }

        print("=== DEBUG[stt]: STT result to client ===", result)
        return result

    except Exception as e:
        print("=== DEBUG[stt]: STT ERROR ===", repr(e))
        raise HTTPException(status_code=500, detail=f"STT failed: {e}")
