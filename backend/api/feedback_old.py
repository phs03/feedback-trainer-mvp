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
    # 프론트에서 보내주는 SPEAKER_00 → "지도전문의"/"전공의" 매핑
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

    # 요청에서 segments와 speaker_mapping 정리
    segments = payload.segments or []
    speaker_mapping = payload.speaker_mapping or {}

    # 🔹 지도전문의로 표시된 segment index 찾기
    supervisor_indices: List[int] = []
    for idx, seg in enumerate(segments):
        role = speaker_mapping.get(seg.speaker, "")
        if role == "지도전문의":
            supervisor_indices.append(idx)

    # 🔹 segments는 있는데, 지도전문의 발언이 하나도 없으면 → LLM 호출하지 않고 "평가 불가/최소점 + 안내" 리턴
    if segments and not supervisor_indices:
        # OSAD을 일단 최소 점수(1점)으로 채워 넣기
        osad_scores = {
            "approach": 1,
            "learning_env": 1,
            "engagement": 1,
            "reaction": 1,
            "reflection": 1,
            "analysis": 1,
            "diagnosis": 1,
            "application": 1,
            "summary": 1,
        }
        osad_scores["total"] = sum(osad_scores.values())
        osad_scores["scale"] = 45

        # evidence는 모두 빈 리스트
        evidence_osad = {
            key: [] for key in [
                "approach",
                "learning_env",
                "engagement",
                "reaction",
                "reflection",
                "analysis",
                "diagnosis",
                "application",
                "summary",
            ]
        }

        return {
            "osad": osad_scores,
            "structure": {
                "has_opening": False,
                "has_core": False,
                "has_closing": False,
            },
            "coach": {
                "strengths": [
                    "이번 녹음에는 전공의의 발언만 있고, 지도전문의의 피드백 발언이 거의(또는 전혀) 없습니다."
                ],
                "improvements_top3": [
                    "OSAD 평가는 지도전문의의 피드백 발언을 기준으로 하기 때문에, 지도전문의가 전공의에게 설명하고 정리하는 발언이 필요합니다.",
                    "전공의가 설명한 뒤, 지도전문의가 관찰·이유·결과·핵심 메시지를 말해 주는 피드백 구조를 의도적으로 만들어 보세요.",
                    "다음에는 지도전문의가 최소 몇 문장 이상 직접 피드백을 말하는 장면이 포함된 녹음을 남겨 주세요.",
                ],
                "script_next_time": (
                    "이번 대화는 대부분 전공의의 설명으로 구성되어 있어 지도전문의 피드백에 대한 OSAD 평가를 수행하기 어렵습니다. "
                    "다음에는 전공의의 설명이 끝난 뒤, 지도전문의가 관찰한 점과 그 이유, 환자에게 미치는 의미, "
                    "다음 진료에서 전공의가 시도해 볼 행동을 정리해서 말해 주는 연습을 해보세요."
                ),
                "micro_habit_10sec": (
                    "피드백 장면이 시작되면 '지금은 전공의에게 구조화된 피드백을 주는 시간이다'라고 마음속으로 정리한 뒤, "
                    "최소 두 문장은 지도전문의가 직접 요약과 조언을 말하는 습관을 들여 보세요."
                ),
            },
            "evidence": {
                "osad": evidence_osad
            },
        }

    # ---------- segments를 인덱스와 함께 문자열로 나열 (role 포함) ----------
    if segments:
        lines = []
        for idx, seg in enumerate(segments):
            role = speaker_mapping.get(seg.speaker, "unknown")
            lines.append(
                f"[{idx}] role={role}, speaker={seg.speaker}, "
                f"start={seg.start}, end={seg.end}, text=\"{seg.text}\""
            )
        segments_desc = "\n".join(lines)
    else:
        segments_desc = "(segments not provided)"

    context_desc = ""
    if payload.context:
        context_desc = (
            f"case={payload.context.case}, "
            f"note={payload.context.note}"
        )

    # ---------- 프롬프트 구성 ----------
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
        "Write all explanation texts (strings) in Korean.\n"
    )

    user_prompt = (
        f"Language: {payload.language}\n"
        f"Trainee level: {payload.trainee_level}\n"
        f"Context: {context_desc}\n\n"
        "Conversation transcript (full text):\n"
        "------------------------------------\n"
        f"{transcript}\n\n"
        "Segments with indices:\n"
        "------------------------------------\n"
        f"{segments_desc}\n\n"
        "Now analyze this feedback conversation using the OSAD framework and "
        "respond ONLY with a JSON object following the required schema."
    )

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
