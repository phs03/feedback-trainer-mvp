# backend/api/feedback.py

import json
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# STT에서 이미 만든 OpenAI client 재사용
from backend.api.stt import client as openai_client


# ---------- 스케일 설정 (확장 가능) ----------

SCALE_CONFIG: Dict[str, Dict[str, Any]] = {
    # 기본 OSAD (지도전문의 피드백용)
    "OSAD_DEBRIEFER": {
        "id": "OSAD_DEBRIEFER",
        "label": "OSAD (Objective Structured Assessment of Debriefing) for Debriefer",
        "max_per_item": 5,
        "num_items": 9,
        "max_total": 45,  # 9개 항목 × 5점 = 45
        "dimensions": [
            "approach",
            "learning_env",
            "engagement",
            "reaction",
            "reflection",
            "analysis",
            "diagnosis",
            "application",
            "summary",
        ],
    },
    # TODO: 나중에 다른 스케일 추가 예정 (예: 전공의-환자, 부모-자녀 등)
    # "CCG_CONSULT": {...},
    # "EMOTION_COACHING_PARENT": {...},
}


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

    # 스케일/시나리오 정보 (일반화 포인트)
    # 프론트에서 안 보내면 기본값으로 OSAD_DEBRIEFER / EM_DEBRIEF 사용
    scale_code: Optional[str] = "OSAD_DEBRIEFER"
    scenario_code: Optional[str] = "EM_DEBRIEF"

    transcript: str = Field(..., description="전체 대화 transcript")
    trainee_level: Optional[str] = "PGY-2"
    language: str = "ko"

    context: Optional[FeedbackContext] = None
    segments: Optional[List[Segment]] = None
    # 프론트에서 보내는 SPEAKER_00 → "지도전문의"/"전공의" 매핑
    speaker_mapping: Optional[Dict[str, str]] = None


# 코칭 리포트에 대한 전반적 도움 정도(1~5점)를 받는 요청 모델
class CoachEvalRequest(BaseModel):
    encounter_id: Optional[str] = None
    supervisor_id: Optional[str] = None
    trainee_id: Optional[str] = None

    scenario_code: str = "EM_DEBRIEF"
    scale_code: str = "OSAD_DEBRIEFER"
    model_version: Optional[str] = "gpt-4o-mini-osad-v1"

    helpful_score: int = Field(..., ge=1, le=5, description="1~5점 Likert")
    # 프론트에서 "기록"으로 체크한 항목들을 helpful_flags로 같이 보낼 수 있음
    helpful_flags: Optional[List[str]] = None
    comment: Optional[str] = None


# 코칭 리포트의 특정 섹션(강점/개선점/스크립트/미세습관)을 저장하기 위한 요청 모델
class CoachMemoRequest(BaseModel):
    encounter_id: Optional[str] = None
    supervisor_id: Optional[str] = None
    trainee_id: Optional[str] = None

    scenario_code: str = "EM_DEBRIEF"
    scale_code: str = "OSAD_DEBRIEFER"
    model_version: Optional[str] = "gpt-4o-mini-osad-v1"

    # saved_sections: {
    #   "strengths": "...\n...",
    #   "improvements_top3": "...\n...",
    #   "script_next_time": "...",
    #   "micro_habit_10sec": "..."
    # }
    saved_sections: Dict[str, str]
    note: Optional[str] = None


router = APIRouter(tags=["feedback"])


@router.post("/feedback")
async def analyze_feedback(payload: FeedbackRequest) -> Dict[str, Any]:
    """
    지도전문의 피드백 대화를 (기본: OSAD_DEBRIEFER 스케일) 기준으로 분석하고,
    각 항목의 근거가 된 segment index를 evidence로 함께 돌려준다.

    기본 응답 구조 예시(OSAD_DEBRIEFER):

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
        "scale": 45,
        "percent": 71.1
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

    # ---------- 어떤 스케일을 사용할지 결정 ----------
    # 프론트가 안 보내면 OSAD_DEBRIEFER 기본 사용
    scale_code = (payload.scale_code or "OSAD_DEBRIEFER").upper()
    if scale_code not in SCALE_CONFIG:
        # 아직 구현되지 않은 스케일이면 OSAD_DEBRIEFER로 fallback
        scale_code = "OSAD_DEBRIEFER"
    scale_cfg = SCALE_CONFIG[scale_code]
    max_total = scale_cfg["max_total"]
    dimensions = scale_cfg["dimensions"]

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
        "You are an expert in medical education and feedback.\n"
        f"You are now using a feedback scale with code: {scale_code}, "
        f"label: {scale_cfg['label']}.\n"
        "For this MVP, the JSON key for scores is still named 'osad', and "
        "the dimensions correspond to the OSAD (Objective Structured Assessment of Debriefing) framework.\n"
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
        f'    \"scale\": int (use {max_total} as the maximum total score for this scale),\n'
        '    \"percent\": number (0-100, optional)\n'
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
        "focus your scoring and coaching mainly on the supervisor's feedback behaviour.\n"
    )

    # ---------- user 프롬프트 ----------
    user_prompt_parts = [
        f"Language code from client: {payload.language}",
        f"Trainee level: {payload.trainee_level}",
        f"Scenario code: {payload.scenario_code}",
        f"Scale code: {scale_code}",
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
                "When scoring and generating coaching tips, "
                "prioritize the supervisor-only speech above.",
            ]
        )

    user_prompt_parts.append(
        "\nNow analyze this feedback conversation using the specified scale "
        "and respond ONLY with a JSON object following the required schema."
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

        # ---------- total / scale / percent 보정 (없으면 계산) ----------
        osad = data.get("osad", {})

        # total이 없으면 스케일의 dimensions 리스트를 기준으로 합산
        if "total" not in osad:
            numeric_scores: List[int] = []
            for dim in dimensions:
                val = osad.get(dim)
                if isinstance(val, int):
                    numeric_scores.append(val)
            osad["total"] = sum(numeric_scores)

        # 항상 이 스케일의 만점은 config에 정의된 값으로 강제
        osad["scale"] = max_total

        total_val = osad.get("total")
        scale_val = max_total

        # percent(0~100%) 계산: (total / scale_val) * 100
        if isinstance(total_val, (int, float)) and scale_val > 0:
            osad.setdefault(
                "percent",
                round(total_val / scale_val * 100, 1),
            )
        else:
            osad.setdefault("percent", 0.0)

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


# ---------- 코칭 리포트에 대한 전반적 도움 정도 평가 저장 ----------

@router.post("/feedback/coach-eval")
async def eval_coaching_report(payload: CoachEvalRequest) -> Dict[str, Any]:
    """
    프론트에서 받은 '이 코칭 리포트가 얼마나 도움이 되었는지(1~5점)' 평가를 수집하는 엔드포인트.

    현재 단계:
      - 실제 DB 저장 대신, 서버 로그에 출력하고 그대로 echo 형태로 반환.
      - 나중에 DB 모델이 준비되면 이 함수 내부에서 insert 하도록 교체.
    """
    try:
        print("=== DEBUG: coach-eval payload ===", payload.dict())
        return {
            "status": "ok",
            "message": "coach-eval 수집 완료 (현재는 로그만 저장)",
            "data": payload.dict(),
        }
    except Exception as e:
        print("=== DEBUG: /feedback/coach-eval ERROR ===", repr(e))
        raise HTTPException(
            status_code=500,
            detail=f"Coach evaluation save failed: {e}",
        )


# ---------- 코칭 리포트에서 '기록'으로 체크한 섹션 저장 ----------

@router.post("/feedback/coach-memo")
async def save_coaching_memo(payload: CoachMemoRequest) -> Dict[str, Any]:
    """
    사용자가 '기록' 체크박스를 통해 선택한 코칭 리포트 섹션을 저장하는 엔드포인트.

    현재 단계:
      - 실제 DB 저장 대신, 서버 로그에 출력하고 그대로 echo 형태로 반환.
      - 나중에 '지도전문의 마이페이지 / 히스토리' 화면에서 볼 수 있도록 DB에 저장하도록 확장.
    """
    try:
        print("=== DEBUG: coach-memo payload ===", payload.dict())
        return {
            "status": "ok",
            "message": "coach-memo 저장 완료 (현재는 로그만 저장)",
            "data": payload.dict(),
        }
    except Exception as e:
        print("=== DEBUG: /feedback/coach-memo ERROR ===", repr(e))
        raise HTTPException(
            status_code=500,
            detail=f"Coach memo save failed: {e}",
        )
