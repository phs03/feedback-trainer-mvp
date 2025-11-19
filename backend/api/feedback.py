# backend/api/feedback.py

import json
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# STT에서 이미 만든 OpenAI client 재사용
from backend.api.stt import client as openai_client


# ---------- Pydantic 모델 ----------

class Segment(BaseModel):
    speaker: str
    start: Optional[float] = None
    end: Optional[float] = None
    text: str


class FeedbackContext(BaseModel):
    case: Optional[str] = None
    language: Optional[str] = None
    note: Optional[str] = None


class FeedbackRequest(BaseModel):
    encounter_id: Optional[str] = None
    supervisor_id: Optional[str] = None
    trainee_id: Optional[str] = None
    audio_ref: Optional[str] = None

    transcript: str = Field(..., description="전체 대화 transcript")
    trainee_level: Optional[str] = "PGY-2"
    language: str = "ko"

    context: Optional[FeedbackContext] = None
    segments: Optional[List[Segment]] = None
    # 🔹 프론트에서 보내는 SPEAKER_00 → "지도전문의"/"전공의" 매핑
    speaker_mapping: Optional[Dict[str, str]] = None


router = APIRouter(tags=["feedback"])


@router.post("/feedback")
async def analyze_feedback(payload: FeedbackRequest) -> Dict[str, Any]:
    """
    지도전문의 피드백 대화를 OSAD 기준으로 분석하고,
    각 OSAD 항목의 근거가 된 segment index를 evidence로 함께 돌려준다.

    프론트에서 기대하는 응답 구조 예시:

    {
      "osad": {
        "approach": 4,
        "learning_env": 3,
        "engagement": 4,
        "reaction": 3,
        "reflection": 4,
        "analysis": 3,
        "diagnosis": 3,
        "application": 4,
        "summary": 4,
        "total": 32,
        "scale": 45
      },
      "structure": {
        "has_opening": true,
        "has_core": true,
        "has_closing": false
      },
      "coach": {
        "strengths": ["...", "..."],
        "improvements_top3": ["...", "...", "..."],
        "script_next_time": "...",
        "micro_habit_10sec": "..."
      },
      "evidence": {
        "osad": {
          "approach": [0, 2],
          "learning_env": [1],
          "engagement": [3],
          "reaction": [4],
          "reflection": [5],
          "analysis": [6],
          "diagnosis": [7],
          "application": [8],
          "summary": [9]
        }
      }
    }
    """

    transcript = payload.transcript.strip()

    # ---------- segments 전체를 인덱스와 함께 문자열로 나열 (디버깅 & evidence 용) ----------
    if payload.segments:
        lines = []
        for idx, seg in enumerate(payload.segments):
            lines.append(
                f"[{idx}] speaker={seg.speaker}, "
                f"start={seg.start}, end={seg.end}, text=\"{seg.text}\""
            )
        segments_desc = "\n".join(lines)
    else:
        segments_desc = "(segments not provided)"

    # ---------- speaker_mapping을 이용해 '지도전문의 발언'만 따로 모으기 ----------
    supervisor_only_text = ""
    if payload.segments and payload.speaker_mapping:
        supervisor_lines: List[str] = []
        for seg in payload.segments:
            role = payload.speaker_mapping.get(seg.speaker)
            if role == "지도전문의":
                supervisor_lines.append(seg.text)
        if supervisor_lines:
            supervisor_only_text = "\n".join(supervisor_lines)

    context_desc = ""
    if payload.context:
        context_desc = (
            f"case={payload.context.case}, "
            f"note={payload.context.note}"
        )

    # ---------- 출력 언어 결정 ----------
    lang_code = (payload.language or "ko").lower()
    lang_name_map = {
        "ko": "Korean",
        "en": "English",
        "zh": "Chinese",
        "es": "Spanish",
        "ja": "Japanese",
        "fr": "French",
        "de": "German",
        "auto": "auto",  # 아래 lang_instruction에서 따로 처리
    }
    output_lang_name = lang_name_map.get(
        lang_code, "the same language as the conversation"
    )

    # ---------- 언어 지침 문장 ----------
    if lang_code == "auto":
        # 자동 모드: 지도전문의 발언의 언어를 추론해서 그 언어로 쓰게 지시
        lang_instruction = (
            "Infer the primary language used by the supervisor in the conversation "
            "(especially from the 'Supervisor-only speech' section). "
            "Write all explanation texts (strings) in that language. "
            "If you cannot clearly infer the language, default to Korean."
        )
    else:
        lang_instruction = (
            f"Write all explanation texts (strings) in {output_lang_name}."
        )

    # ---------- system 프롬프트 ----------
    system_prompt = (
        "You are an expert in medical education and feedback, "
        "using the OSAD (Objective Structured Assessment of Debriefing) framework.\n"
        "You analyze a debriefing/feedback conversation between a supervisor "
        "and a trainee (resident), then score it and provide coaching tips.\n\n"
        "You MUST reply in a single valid JSON object ONLY, with this schema:\n"
        "{\n"
        '  \"osad\": {\n'
        '    \"approach\": int (1-5),\n'
        '    \"learning_env\": int (1-5),\n'
        '    \"engagement\": int (1-5),\n'
        '    \"reaction\": int (1-5),\n'
        '    \"reflection\": int (1-5),\n'
        '    \"analysis\": int (1-5),\n'
        '    \"diagnosis\": int (1-5),\n'
        '    \"application\": int (1-5),\n'
        '    \"summary\": int (1-5),\n'
        '    \"total\": int,\n'
        '    \"scale\": int\n'
        "  },\n"
        '  \"structure\": {\n'
        '    \"has_opening\": bool,\n'
        '    \"has_core\": bool,\n'
        '    \"has_closing\": bool\n'
        "  },\n"
        '  \"coach\": {\n'
        '    \"strengths\": [string, ...],\n'
        '    \"improvements_top3\": [string, ...],\n'
        '    \"script_next_time\": string,\n'
        '    \"micro_habit_10sec\": string\n'
        "  },\n"
        '  \"evidence\": {\n'
        '    \"osad\": {\n'
        '      \"approach\": [int, ...],\n'
        '      \"learning_env\": [int, ...],\n'
        '      \"engagement\": [int, ...],\n'
        '      \"reaction\": [int, ...],\n'
        '      \"reflection\": [int, ...],\n'
        '      \"analysis\": [int, ...],\n'
        '      \"diagnosis\": [int, ...],\n'
        '      \"application\": [int, ...],\n'
        '      \"summary\": [int, ...]\n'
        "    }\n"
        "  }\n"
        "}\n\n"
        "All evidence indices must refer to the segment indices given in the input.\n"
        "Use only indices that exist. If there is no clear evidence, use an empty list.\n"
        f"{lang_instruction}\n"
        "If only the supervisor's speech is provided separately, "
        "focus your OSAD scoring and coaching mainly on the supervisor's feedback behaviour.\n"
    )

    # ---------- user 프롬프트 ----------
    user_prompt_parts = [
        f"Language code from client: {payload.language}",
        f"Trainee level: {payload.trainee_level}",
        f"Context: {context_desc}",
        "",
        "Full conversation transcript:",
        "------------------------------------",
        transcript,
        "",
        "Segments with indices:",
        "------------------------------------",
        segments_desc,
    ]

    if supervisor_only_text:
        user_prompt_parts.extend(
            [
                "",
                "Supervisor-only speech (extracted from segments based on speaker_mapping):",
                "------------------------------------",
                supervisor_only_text,
                "",
                "When scoring OSAD and generating coaching tips, "
                "prioritize the supervisor-only speech above.",
            ]
        )

    user_prompt_parts.append(
        "\nNow analyze this feedback conversation using the OSAD framework and "
        "respond ONLY with a JSON object following the required schema."
    )

    user_prompt = "\n".join(user_prompt_parts)

    try:
        # ---------- ChatCompletion 호출 (JSON 모드) ----------
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        content = resp.choices[0].message.content
        data = json.loads(content)

        # ---------- total / scale 보정 (없으면 계산) ----------
        osad = data.get("osad", {})
        if "total" not in osad:
            numeric_scores = [
                osad.get("approach"),
                osad.get("learning_env"),
                osad.get("engagement"),
                osad.get("reaction"),
                osad.get("reflection"),
                osad.get("analysis"),
                osad.get("diagnosis"),
                osad.get("application"),
                osad.get("summary"),
            ]
            osad["total"] = sum(x for x in numeric_scores if isinstance(x, int))
        if "scale" not in osad:
            osad["scale"] = 45
        data["osad"] = osad

        # ---------- evidence.osad 기본 구조 보정 ----------
        if "evidence" not in data:
            data["evidence"] = {"osad": {}}
        else:
            if "osad" not in data["evidence"]:
                data["evidence"]["osad"] = {}

        return data

    except json.JSONDecodeError as je:
        print("=== DEBUG: /feedback JSON decode error ===", repr(je))
        print("=== DEBUG: raw content ===", content)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse LLM JSON: {je}",
        )
    except Exception as e:
        print("=== DEBUG: /feedback ERROR ===", repr(e))
        raise HTTPException(
            status_code=500,
            detail=f"Feedback analysis failed: {e}",
        )
