# backend/api/feedback.py

import json
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

# STT에서 이미 만든 OpenAI client 재사용
from backend.api.stt import client as openai_client

# DB 관련
from backend.db import get_db
from backend.models.feedback_models import CoachEval, CoachMemo


# ---------- 스케일 설정 (OSAD + OMP 호환) ----------

SCALE_CONFIG: Dict[str, Dict[str, Any]] = {
    "OSAD_DEBRIEFER": {
        "id": "OSAD_DEBRIEFER",
        "label": (
            "OSAD (Objective Structured Assessment of Debriefing) "
            "for Debriefer"
        ),
        "max_per_item": 5,
        "num_items": 9,
        "max_total": 45,
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
    "OMP_CLINICAL": {
        "id": "OMP_CLINICAL",
        "label": "One-Minute Preceptor (OMP) Clinical Teaching Scale",
        "max_per_item": 5,
        "num_items": 5,
        "max_total": 25,
        "dimensions": [
            "get_commitment",
            "probe_for_evidence",
            "teach_general_rules",
            "reinforce_what_was_done_right",
            "correct_mistakes",
        ],
        "dimension_labels": {
            "get_commitment": (
                "의견·진단·계획에 대한 전공의 입장 끌어내기 "
                "(Get a commitment)"
            ),
            "probe_for_evidence": (
                "판단의 근거를 질문하고 탐색하기 "
                "(Probe for supporting evidence)"
            ),
            "teach_general_rules": (
                "적용 가능한 일반 원칙/규칙을 가르치기 "
                "(Teach general rules)"
            ),
            "reinforce_what_was_done_right": (
                "잘한 부분을 구체적으로 강화하기 "
                "(Reinforce what was done right)"
            ),
            "correct_mistakes": (
                "실수나 부족한 부분을 바로잡아 주기 "
                "(Correct mistakes)"
            ),
        },
    },
}

# 현재 프런트엔드에서 사용하는 코드와 기존 백엔드 코드를 모두 허용
SCALE_ALIASES: Dict[str, str] = {
    "OMP_CORE_FIVE": "OMP_CLINICAL",
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

    # OMP를 기본값으로 사용
    scale_code: Optional[str] = "OMP_CORE_FIVE"
    scenario_code: Optional[str] = "CLINICAL_OMP"

    transcript: str = Field(..., description="전체 대화 transcript")
    trainee_level: Optional[str] = "PGY-2"
    language: str = "ko"

    context: Optional[FeedbackContext] = None
    segments: Optional[List[Segment]] = None

    # auto: AI가 화자 역할을 추론
    # manual: Advanced Mode에서 사용자가 직접 지정
    speaker_mode: Literal["auto", "manual"] = "auto"

    # SPEAKER_00 → 지도전문의/전공의/기타
    # manual 모드에서만 확정값으로 사용
    speaker_mapping: Optional[Dict[str, str]] = None


class CoachEvalRequest(BaseModel):
    encounter_id: Optional[str] = None
    supervisor_id: Optional[str] = None
    trainee_id: Optional[str] = None

    scenario_code: str = "CLINICAL_OMP"
    scale_code: str = "OMP_CORE_FIVE"
    model_version: Optional[str] = "gpt-4o-mini-omp-v1"

    helpful_score: int = Field(..., ge=1, le=5, description="1~5점 Likert")
    helpful_flags: Optional[List[str]] = None
    comment: Optional[str] = None


class CoachMemoRequest(BaseModel):
    encounter_id: Optional[str] = None
    supervisor_id: Optional[str] = None
    trainee_id: Optional[str] = None

    scenario_code: str = "CLINICAL_OMP"
    scale_code: str = "OMP_CORE_FIVE"
    model_version: Optional[str] = "gpt-4o-mini-omp-v1"

    saved_sections: Dict[str, str]
    note: Optional[str] = None


router = APIRouter(tags=["feedback"])


# ---------- 보조 함수 ----------

def normalize_scale_code(raw_scale_code: Optional[str]) -> str:
    """프런트엔드 별칭을 실제 백엔드 스케일 코드로 정규화한다."""
    requested = (raw_scale_code or "OMP_CORE_FIVE").upper()
    effective = SCALE_ALIASES.get(requested, requested)

    if effective not in SCALE_CONFIG:
        effective = "OMP_CLINICAL"

    return effective


def normalize_role_label(role: Any) -> str:
    """
    AI 또는 사용자가 반환한 다양한 역할 표현을
    지도전문의/전공의/기타로 정규화한다.
    """
    value = str(role or "").strip()
    lowered = value.lower()

    supervisor_terms = {
        "지도전문의",
        "supervisor",
        "preceptor",
        "faculty",
        "attending",
        "teacher",
        "educator",
        "instructor",
    }
    trainee_terms = {
        "전공의",
        "trainee",
        "resident",
        "learner",
        "student",
    }

    if value == "지도전문의" or lowered in supervisor_terms:
        return "지도전문의"
    if value == "전공의" or lowered in trainee_terms:
        return "전공의"

    return "기타"


def normalize_manual_mapping(
    mapping: Optional[Dict[str, str]],
) -> Dict[str, str]:
    """수동 화자 매핑 값을 표준 역할 라벨로 정리한다."""
    if not mapping:
        return {}

    return {
        str(speaker): normalize_role_label(role)
        for speaker, role in mapping.items()
    }


def get_observed_speakers(
    segments: Optional[List[Segment]],
) -> List[str]:
    """segments에 실제로 나타난 화자 라벨을 순서대로 반환한다."""
    observed: List[str] = []

    for segment in segments or []:
        speaker = str(segment.speaker or "").strip()
        if speaker and speaker not in observed:
            observed.append(speaker)

    return observed


def validate_manual_mapping(
    segments: Optional[List[Segment]],
    mapping: Dict[str, str],
) -> None:
    """Advanced Mode의 수동 매핑이 분석에 충분한지 검사한다."""
    if not mapping:
        raise HTTPException(
            status_code=422,
            detail="Manual speaker mode requires speaker_mapping.",
        )

    observed_speakers = get_observed_speakers(segments)

    if observed_speakers:
        missing = [
            speaker
            for speaker in observed_speakers
            if speaker not in mapping
        ]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Manual speaker mapping is missing the following "
                    f"speakers: {missing}"
                ),
            )

    if "지도전문의" not in set(mapping.values()):
        raise HTTPException(
            status_code=422,
            detail=(
                "Manual speaker mapping must identify at least one "
                "speaker as 지도전문의."
            ),
        )


def build_segments_description(
    segments: Optional[List[Segment]],
) -> str:
    """LLM 입력용 diarization segment 문자열을 만든다."""
    if not segments:
        return "(segments not provided)"

    lines: List[str] = []
    for idx, segment in enumerate(segments):
        text = (segment.text or "").strip()
        lines.append(
            f'[{idx}] speaker={segment.speaker}, '
            f"start={segment.start}, end={segment.end}, "
            f'text="{text}"'
        )

    return "\n".join(lines)


def extract_supervisor_speech(
    segments: Optional[List[Segment]],
    mapping: Dict[str, str],
) -> str:
    """manual 모드에서 지도전문의 발화만 추출한다."""
    lines: List[str] = []

    for segment in segments or []:
        role = mapping.get(segment.speaker)
        text = (segment.text or "").strip()

        if role == "지도전문의" and text:
            lines.append(text)

    return "\n".join(lines)


def confidence_label_from_value(value: float) -> str:
    if value >= 0.8:
        return "high"
    if value >= 0.6:
        return "medium"
    return "low"


def normalize_speaker_analysis(
    raw_analysis: Any,
    *,
    speaker_mode: str,
    observed_speakers: List[str],
    manual_mapping: Dict[str, str],
) -> Dict[str, Any]:
    """
    LLM의 speaker_analysis를 프런트엔드가 안정적으로 사용할 수 있는
    구조로 보정한다.
    """
    if speaker_mode == "manual":
        return {
            "mode": "manual",
            "mapping": manual_mapping,
            "confidence": 1.0,
            "confidence_label": "high",
            "uncertain": False,
            "reason": "Advanced Mode에서 사용자가 화자 역할을 직접 지정했습니다.",
        }

    analysis = raw_analysis if isinstance(raw_analysis, dict) else {}

    raw_mapping = analysis.get("mapping")
    normalized_mapping: Dict[str, str] = {}

    if isinstance(raw_mapping, dict):
        for speaker, role in raw_mapping.items():
            normalized_mapping[str(speaker)] = normalize_role_label(role)

    # 관찰된 화자가 응답에서 누락되면 기타로 보완
    for speaker in observed_speakers:
        normalized_mapping.setdefault(speaker, "기타")

    raw_confidence = analysis.get("confidence", 0.0)
    try:
        confidence = float(raw_confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    confidence = min(1.0, max(0.0, confidence))
    confidence_label = confidence_label_from_value(confidence)

    uncertain = bool(analysis.get("uncertain", False))

    supervisor_count = sum(
        1
        for role in normalized_mapping.values()
        if role == "지도전문의"
    )
    trainee_count = sum(
        1
        for role in normalized_mapping.values()
        if role == "전공의"
    )

    # 2인 대화인데 핵심 역할이 모두 확인되지 않으면 불확실 처리
    if len(observed_speakers) < 2:
        uncertain = True
    if supervisor_count == 0 or trainee_count == 0:
        uncertain = True
    if confidence < 0.6:
        uncertain = True

    reason = str(
        analysis.get("reason")
        or "화자 역할 추론 근거가 충분히 반환되지 않았습니다."
    )

    return {
        "mode": "auto",
        "mapping": normalized_mapping,
        "confidence": confidence,
        "confidence_label": confidence_label,
        "uncertain": uncertain,
        "reason": reason,
    }


def normalize_scores(
    raw_scores: Any,
    dimensions: List[str],
    max_total: int,
) -> Dict[str, Any]:
    """
    기존 프런트엔드 호환성을 위해 점수 객체 키는 osad를 유지한다.
    OMP 모드에서는 이 안에 OMP 5개 microskill 점수가 들어간다.
    """
    scores = raw_scores if isinstance(raw_scores, dict) else {}

    normalized: Dict[str, Any] = {}

    for dimension in dimensions:
        raw_value = scores.get(dimension)
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            value = 1

        normalized[dimension] = min(5, max(1, value))

    total = sum(normalized[dimension] for dimension in dimensions)
    normalized["total"] = total
    normalized["scale"] = max_total
    normalized["percent"] = (
        round(total / max_total * 100, 1)
        if max_total > 0
        else 0.0
    )

    return normalized


def normalize_evidence(
    raw_evidence: Any,
    dimensions: List[str],
    segment_count: int,
) -> Dict[str, Dict[str, List[int]]]:
    """존재하는 segment index만 evidence에 남긴다."""
    evidence_root = raw_evidence if isinstance(raw_evidence, dict) else {}
    raw_scale_evidence = evidence_root.get("osad")

    if not isinstance(raw_scale_evidence, dict):
        raw_scale_evidence = {}

    normalized_scale_evidence: Dict[str, List[int]] = {}

    for dimension in dimensions:
        raw_indices = raw_scale_evidence.get(dimension, [])
        valid_indices: List[int] = []

        if isinstance(raw_indices, list):
            for index in raw_indices:
                if isinstance(index, int) and 0 <= index < segment_count:
                    if index not in valid_indices:
                        valid_indices.append(index)

        normalized_scale_evidence[dimension] = valid_indices

    return {"osad": normalized_scale_evidence}


# ---------- 피드백 분석 ----------

@router.post("/feedback")
async def analyze_feedback(payload: FeedbackRequest) -> Dict[str, Any]:
    """
    기본 모드에서는 AI가 익명 화자의 역할을 추론한 뒤 지도전문의의
    OMP 교수행동을 평가한다.

    Advanced Mode에서는 사용자가 지정한 화자 역할을 확정값으로 사용한다.
    기존 프런트엔드 호환성을 위해 점수 객체와 evidence 키는 osad를 유지한다.
    """

    transcript = payload.transcript.strip()
    if not transcript:
        raise HTTPException(
            status_code=422,
            detail="transcript must not be empty.",
        )

    speaker_mode = payload.speaker_mode

    requested_scale_code = (
        payload.scale_code or "OMP_CORE_FIVE"
    ).upper()
    effective_scale_code = normalize_scale_code(
        requested_scale_code
    )

    scale_cfg = SCALE_CONFIG[effective_scale_code]
    max_total: int = scale_cfg["max_total"]
    dimensions: List[str] = scale_cfg["dimensions"]
    dimension_labels: Dict[str, str] = scale_cfg.get(
        "dimension_labels",
        {},
    )

    observed_speakers = get_observed_speakers(
        payload.segments,
    )

    manual_mapping: Dict[str, str] = {}
    supervisor_only_text = ""

    if speaker_mode == "manual":
        manual_mapping = normalize_manual_mapping(
            payload.speaker_mapping,
        )
        validate_manual_mapping(
            payload.segments,
            manual_mapping,
        )
        supervisor_only_text = extract_supervisor_speech(
            payload.segments,
            manual_mapping,
        )

    # ---------- JSON 스키마 문자열 동적 생성 ----------

    score_schema_lines = [
        f'    "{dimension}": int (1-5),\n'
        for dimension in dimensions
    ]
    score_schema_text = "".join(score_schema_lines)

    evidence_schema_lines = [
        f'      "{dimension}": [int, ...],\n'
        for dimension in dimensions
    ]
    evidence_schema_text = "".join(
        evidence_schema_lines
    )

    dimension_desc_text = ""
    if dimension_labels:
        dimension_desc_text = "\n".join(
            (
                f"- {dimension}: "
                f"{dimension_labels.get(dimension, dimension)}"
            )
            for dimension in dimensions
        )

    segments_desc = build_segments_description(
        payload.segments,
    )

    context_desc = ""
    if payload.context:
        context_desc = (
            f"case={payload.context.case}, "
            f"note={payload.context.note}"
        )

    # ---------- 출력 언어 ----------

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
        lang_code,
        "the same language as the conversation",
    )

    if lang_code == "auto":
        lang_instruction = (
            "Infer the primary language used by the supervisor from the "
            "conversation and write every explanatory string in that "
            "language. If unclear, default to Korean."
        )
    else:
        lang_instruction = (
            f"Write every explanatory string in {output_lang_name}."
        )

    # ---------- 역할 추론 및 평가 프롬프트 ----------

    system_prompt = (
        "You are an expert medical educator evaluating a short clinical "
        "teaching conversation between a supervisor and a trainee.\n\n"

        f"Speaker mode: {speaker_mode}\n"

        "ROLE RULES\n"
        "- If speaker mode is auto, infer the role of every anonymous "
        "speaker from conversational function, not from the speaker number.\n"
        "- Do not assume SPEAKER_00 is the supervisor.\n"
        "- A supervisor commonly asks for a clinical commitment, probes "
        "reasoning, teaches general rules, reinforces strengths, or corrects "
        "mistakes and omissions.\n"
        "- A trainee commonly presents a clinical judgment, explains "
        "reasoning, answers questions, or reflects on performance.\n"
        "- If roles are not clear, mark uncertain=true and lower confidence.\n"
        "- If speaker mode is manual, the supplied speaker mapping is "
        "authoritative. Do not reinterpret or reverse it.\n"
        "- In the JSON mapping, use only these exact Korean role labels: "
        "지도전문의, 전공의, 기타.\n\n"

        "SCORING RULES\n"
        f"- Requested scale code: {requested_scale_code}\n"
        f"- Effective scale code: {effective_scale_code}\n"
        f"- Scale label: {scale_cfg['label']}\n"
        "- First determine the roles, then evaluate only the supervisor's "
        "observable clinical teaching and feedback behaviours.\n"
        "- Do not give credit for a behaviour performed only by the trainee.\n"
        "- Score only behaviours that are supported by the transcript or "
        "indexed segments.\n"
        "- Each item must be an integer from 1 to 5.\n"
        "- Evidence must contain only valid segment indices.\n"
        "- If no clear evidence exists for an item, return an empty list.\n"
        "- Return JSON only.\n\n"
    )

    if dimension_desc_text:
        system_prompt += (
            "SCALE DIMENSIONS\n"
            f"{dimension_desc_text}\n\n"
        )

    system_prompt += (
        "REQUIRED JSON SCHEMA\n"
        "{\n"
        '  "speaker_analysis": {\n'
        '    "mode": "auto or manual",\n'
        '    "mapping": {"SPEAKER_00": "지도전문의|전공의|기타"},\n'
        '    "confidence": number between 0 and 1,\n'
        '    "confidence_label": "high|medium|low",\n'
        '    "uncertain": bool,\n'
        '    "reason": string\n'
        "  },\n"
        '  "osad": {\n'
        f"{score_schema_text}"
        '    "total": int,\n'
        f'    "scale": {max_total},\n'
        '    "percent": number between 0 and 100\n'
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
        f"{lang_instruction}\n"
    )

    manual_mapping_desc = (
        json.dumps(
            manual_mapping,
            ensure_ascii=False,
        )
        if manual_mapping
        else "(not provided)"
    )

    user_prompt_parts = [
        f"Speaker mode: {speaker_mode}",
        f"Manual speaker mapping: {manual_mapping_desc}",
        f"Language code from client: {payload.language}",
        f"Trainee level: {payload.trainee_level}",
        f"Scenario code: {payload.scenario_code}",
        f"Requested scale code: {requested_scale_code}",
        f"Effective scale code: {effective_scale_code}",
        f"Context: {context_desc}",
        "",
        "Full conversation transcript:",
        "------------------------------------",
        transcript,
        "",
        "Diarized segments with indices:",
        "------------------------------------",
        segments_desc,
    ]

    if speaker_mode == "auto":
        user_prompt_parts.extend(
            [
                "",
                "Automatic role inference instruction:",
                "------------------------------------",
                (
                    "Infer which speaker is the supervisor and which is "
                    "the trainee from the functions of their utterances. "
                    "Then score only the supervisor's behaviours."
                ),
            ]
        )

    if speaker_mode == "manual":
        user_prompt_parts.extend(
            [
                "",
                "Manual role instruction:",
                "------------------------------------",
                (
                    "Use the supplied mapping as the final role assignment. "
                    "Do not change it."
                ),
            ]
        )

        if supervisor_only_text:
            user_prompt_parts.extend(
                [
                    "",
                    "Supervisor-only speech extracted from manual mapping:",
                    "------------------------------------",
                    supervisor_only_text,
                    "",
                    (
                        "Use this section as the primary material for "
                        "supervisor scoring and coaching."
                    ),
                ]
            )

    user_prompt_parts.append(
        "\nAnalyze the conversation and return only one JSON object "
        "that follows the required schema."
    )

    user_prompt = "\n".join(user_prompt_parts)

    content = ""

    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
        )

        content = resp.choices[0].message.content or ""
        data = json.loads(content)

        if not isinstance(data, dict):
            raise ValueError(
                "LLM response JSON root must be an object."
            )

        # ---------- 화자 분석 결과 보정 ----------

        data["speaker_analysis"] = normalize_speaker_analysis(
            data.get("speaker_analysis"),
            speaker_mode=speaker_mode,
            observed_speakers=observed_speakers,
            manual_mapping=manual_mapping,
        )

        # ---------- 점수 보정 ----------

        data["osad"] = normalize_scores(
            data.get("osad"),
            dimensions=dimensions,
            max_total=max_total,
        )

        # ---------- evidence 보정 ----------

        data["evidence"] = normalize_evidence(
            data.get("evidence"),
            dimensions=dimensions,
            segment_count=len(payload.segments or []),
        )

        # ---------- 기타 응답 구조 보정 ----------

        if not isinstance(data.get("structure"), dict):
            data["structure"] = {
                "has_opening": False,
                "has_core": False,
                "has_closing": False,
            }

        if not isinstance(data.get("coach"), dict):
            data["coach"] = {
                "strengths": [],
                "improvements_top3": [],
                "script_next_time": "",
                "micro_habit_10sec": "",
            }

        # 프런트엔드 디버깅 및 향후 저장용 메타데이터
        data["meta"] = {
            "speaker_mode": speaker_mode,
            "requested_scale_code": requested_scale_code,
            "effective_scale_code": effective_scale_code,
            "scenario_code": payload.scenario_code,
            "observed_speakers": observed_speakers,
            "model_version": "gpt-4o-mini-omp-v1",
        }

        return data

    except json.JSONDecodeError as exc:
        print(
            "=== DEBUG: /feedback JSON decode error ===",
            repr(exc),
        )
        print("=== DEBUG: raw content ===", content)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse LLM JSON: {exc}",
        ) from exc

    except HTTPException:
        raise

    except Exception as exc:
        print(
            "=== DEBUG: /feedback ERROR ===",
            repr(exc),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Feedback analysis failed: {exc}",
        ) from exc


# ---------- 코칭 리포트 도움 정도 평가 저장 ----------

@router.post("/feedback/coach-eval")
async def eval_coaching_report(
    payload: CoachEvalRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        flags_json = None
        if payload.helpful_flags is not None:
            flags_json = json.dumps(
                payload.helpful_flags,
                ensure_ascii=False,
            )

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

    except Exception as exc:
        print(
            "=== DEBUG: /feedback/coach-eval ERROR ===",
            repr(exc),
        )
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Coach evaluation save failed: {exc}",
        ) from exc


# ---------- 코칭 리포트 선택 섹션 저장 ----------

@router.post("/feedback/coach-memo")
async def save_coaching_memo(
    payload: CoachMemoRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        sections_json = json.dumps(
            payload.saved_sections,
            ensure_ascii=False,
        )

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

    except Exception as exc:
        print(
            "=== DEBUG: /feedback/coach-memo ERROR ===",
            repr(exc),
        )
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Coach memo save failed: {exc}",
        ) from exc
