# backend/api/feedback.py

import json
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

# STT에서 이미 만든 OpenAI client 재사용
from backend.api.stt import client as openai_client

# DB 관련
from backend.db import get_db
from backend.models.feedback_models import CoachEval, CoachMemo


# ---------- 스케일 설정 (OSAD + OMP) ----------

SCALE_CONFIG: Dict[str, Dict[str, Any]] = {
    # 1) 기본 OSAD (지도전문의 피드백용)
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
        # 필요하면 나중에 OSAD 항목 설명도 여기에 추가 가능
        # "dimension_labels": { ... }
    },

    # 2) OMP 임상 피드백 스케일 (원형 5 microskills)
    "OMP_CLINICAL": {
        "id": "OMP_CLINICAL",
        "label": "One-Minute Preceptor (OMP) Clinical Teaching Scale",
        "max_per_item": 5,
        "num_items": 5,
        "max_total": 25,  # 5개 항목 × 5점 = 25
        # JSON 안에서 사용할 키 이름들
        "dimensions": [
            "get_commitment",
            "probe_for_evidence",
            "teach_general_rules",
            "reinforce_what_was_done_right",
            "correct_mistakes",
        ],
        # 🔹 각 항목 제목: 한글 + (영어 원문) 병기
        "dimension_labels": {
            "get_commitment": "의견·진단·계획에 대한 전공의 입장 끌어내기 (Get a commitment)",
            "probe_for_evidence": "판단의 근거를 질문하고 탐색하기 (Probe for supporting evidence)",
            "teach_general_rules": "적용 가능한 일반 원칙/규칙을 가르치기 (Teach general rules)",
            "reinforce_what_was_done_right": "잘한 부분을 구체적으로 강화하기 (Reinforce what was done right)",
            "correct_mistakes": "실수나 부족한 부분을 바로잡아 주기 (Correct mistakes)",
        },
    },
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
    피드백 대화를 (기본: OSAD_DEBRIEFER 스케일, 선택 시: OMP_CLINICAL 등)
    기준으로 분석하고, 각 항목의 근거가 된 segment index를 evidence로 함께 돌려준다.
    """

    transcript = payload.transcript.strip()

    # ---------- 어떤 스케일을 사용할지 결정 ----------
    scale_code = (payload.scale_code or "OSAD_DEBRIEFER").upper()
    if scale_code not in SCALE_CONFIG:
        scale_code = "OSAD_DEBRIEFER"
    scale_cfg = SCALE_CONFIG[scale_code]
    max_total = scale_cfg["max_total"]
    dimensions: List[str] = scale_cfg["dimensions"]
    dimension_labels: Dict[str, str] = scale_cfg.get("dimension_labels", {})

    # ---------- JSON 스키마(점수 / evidence) 문자열 동적 생성 ----------
    # 점수 부분: "osad": { "<dim>": int(1-5), ... }
    score_schema_lines: List[str] = []
    for dim in dimensions:
        score_schema_lines.append(f'    "{dim}": int (1-5),\n')
    score_schema_text = "".join(score_schema_lines)

    # evidence 부분: "evidence": { "osad": { "<dim>": [int, ...], ... } }
    ev_schema_lines: List[str] = []
    for dim in dimensions:
        ev_schema_lines.append(f'      "{dim}": [int, ...],\n')
    evidence_schema_text = "".join(ev_schema_lines)

    # 프롬프트에 보여줄 스케일 항목 설명 (있으면)
    dimension_desc_text = ""
    if dimension_labels:
        desc_lines = []
        for dim in dimensions:
            label = dimension_labels.get(dim, dim)
            desc_lines.append(f"- {dim}: {label}")
        dimension_desc_text = "\n".join(desc_lines)

    # ---------- segments 전체를 인덱스와 함께 문자열로 나열 ----------
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
        "auto": "auto",
    }
    output_lang_name = lang_name_map.get(
        lang_code, "the same language as the conversation"
    )

    # ---------- 언어 지침 문장 ----------
    if lang_code == "auto":
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
        "You analyze a debriefing/feedback conversation between a supervisor "
        "and a trainee (resident), then score it and provide coaching tips.\n\n"
    )

    if dimension_desc_text:
        system_prompt += "This scale has the following dimensions:\n"
        system_prompt += dimension_desc_text + "\n\n"

    system_prompt += (
        "You MUST reply in a single valid JSON object ONLY, with this schema:\n"
        "{\n"
        '  "osad": {\n'
        f"{score_schema_text}"
        '    "total": int,\n'
        f'    "scale": int (use {max_total} as the maximum total score for this scale),\n'
        '    "percent": number (0-100, optional)\n'
        "  },\n"
        '  "structure": {\n'
        '    "has_opening": bool,\n'
        '    "has_core": bool,\n'
        '    "has_closing": bool\n'
        "  },\n"
        '  "coach": {\n'
        '    "strengths": [string, ...],\n'
        '    "improvements_top3": [string, ...],\n'
        '    "script_next_time": string,\n'
        '    "micro_habit_10sec": string\n'
        "  },\n"
        '  "evidence": {\n'
        '    "osad": {\n'
        f"{evidence_schema_text}"
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
async def eval_coaching_report(
    payload: CoachEvalRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    프론트에서 받은 '이 코칭 리포트가 얼마나 도움이 되었는지(1~5점)' 평가를
    coach_eval 테이블에 저장하는 엔드포인트.
    """
    try:
        # helpful_flags는 리스트일 수 있으므로 JSON 문자열로 변환
        flags_json = None
        if payload.helpful_flags is not None:
            flags_json = json.dumps(payload.helpful_flags, ensure_ascii=False)

        obj = CoachEval(
            encounter_id=payload.encounter_id,
            supervisor_id=payload.supervisor_id,
            trainee_id=payload.trainee_id,
            scenario_code=payload.scenario_code,
            scale_code=payload.scale_code,
            model_version=payload.model_version,
            helpful_score=payload.helpful_score,
            helpful_flags=flags_json,
            comment=payload.comment,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)

        return {
            "status": "ok",
            "message": "coach-eval 저장 완료",
            "data": {
                "id": obj.id,
                "encounter_id": obj.encounter_id,
                "helpful_score": obj.helpful_score,
            },
        }
    except Exception as e:
        print("=== DEBUG: /feedback/coach-eval ERROR ===", repr(e))
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Coach evaluation save failed: {e}",
        )


# ---------- 코칭 리포트에서 '기록'으로 체크한 섹션 저장 ----------

@router.post("/feedback/coach-memo")
async def save_coaching_memo(
    payload: CoachMemoRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    사용자가 '기록' 체크박스로 선택한 코칭 리포트 섹션을
    coach_memo 테이블에 저장하는 엔드포인트.
    """
    try:
        # saved_sections(dict)를 JSON 문자열로 저장
        sections_json = json.dumps(payload.saved_sections, ensure_ascii=False)

        obj = CoachMemo(
            encounter_id=payload.encounter_id,
            supervisor_id=payload.supervisor_id,
            trainee_id=payload.trainee_id,
            scenario_code=payload.scenario_code,
            scale_code=payload.scale_code,
            model_version=payload.model_version,
            saved_sections=sections_json,
            note=payload.note,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)

        return {
            "status": "ok",
            "message": "coach-memo 저장 완료",
            "data": {
                "id": obj.id,
                "encounter_id": obj.encounter_id,
            },
        }
    except Exception as e:
        print("=== DEBUG: /feedback/coach-memo ERROR ===", repr(e))
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Coach memo save failed: {e}",
        )
