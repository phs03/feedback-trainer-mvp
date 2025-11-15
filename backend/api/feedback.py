import re
from typing import Optional, List, Dict
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(
    prefix="/feedback",
    tags=["feedback"],
)


# ==============================
#  Pydantic 모델 정의
# ==============================
class OSADScores(BaseModel):
    approach: int = 0
    learning_env: int = 0
    engagement: int = 0
    reaction: int = 0
    reflection: int = 0
    analysis: int = 0
    diagnosis: int = 0
    application: int = 0
    summary: int = 0
    total: int = 0
    scale: int = 45


class Findings(BaseModel):
    talk_listen_ratio: str = "60:40"
    specific_examples: bool = False
    goal_setting: bool = False


class StructureReport(BaseModel):
    has_opening: bool
    has_core: bool
    has_closing: bool


class CoachReport(BaseModel):
    strengths: List[str]
    improvements_top3: List[str]
    script_next_time: str
    micro_habit_10sec: str


class FeedbackIn(BaseModel):
    """
    지도전문의가 전공의에게 한 피드백(녹음 → STT 결과)을 서버로 보내는 요청 형식
    """
    encounter_id: str
    supervisor_id: str
    trainee_id: Optional[str] = None
    audio_ref: Optional[str] = None
    transcript: str = Field(..., description="녹음 STT 결과 텍스트")
    context: Optional[Dict[str, str]] = None


class FeedbackOut(BaseModel):
    """
    OSAD 기반 점수 + 코칭 리포트 응답 형식
    """
    encounter_id: str
    osad: OSADScores
    findings: Findings
    coach: CoachReport
    structure: StructureReport


# ==============================
#  구조 분석 유틸
# ==============================
def split_sentences(text: str) -> list[str]:
    """
    피드백 발화를 문장 단위로 단순 분리
    """
    s = re.split(r"[.!?]\s*", text)
    return [x.strip() for x in s if x.strip()]


def detect_structure(transcript: str) -> dict:
    """
    Opening / Core / Closing 구조 감지
    - Phase 2 + 살짝 완화 버전
    """
    sents = split_sentences(transcript)

    if not sents:
        return {
            "has_opening": False,
            "has_core": False,
            "has_closing": False,
        }

    # ---- 패턴 정의 ----
    # Opening: 대화 초반, 전공의 생각/판단/느낌/설명을 묻는 질문
    opening_q_patterns = [
        "생각은", "생각해", "어때", "어땠",
        "어떻게 판단", "어떻게 느꼈",
        "왜 그렇게", "왜 그랬",
        "설명해", "설명해볼래", "말해볼래"
    ]

    opening_first_patterns = [
        "먼저", "처음에", "우선", "일단"
    ]

    # Core: 관찰(행동) + 이유/결과/영향
    core_observation_patterns = [
        "했을 때", "하는 걸 보니까", "하는 것을 보니까",
        "내가 보기에", "내가 봤을 때",
        "네가 ", "환자에게 설명할 때", "설명했을 때"
    ]

    core_reason_patterns = [
        "그래서", "그 결과", "때문에",
        "영향을 줬", "보였어", "좋아졌어", "나빠졌어",
        # 평가/피드백에서 자주 쓰는 표현들 추가
        "좋았어", "좋았다고", "잘했어", "잘했다고",
        "아쉬웠어", "아쉬운 점", "문제였어", "문제가 있었",
        "위험했어", "위험할 수 있었"
    ]
    
    evaluation_patterns = [
        "좋았어", "좋았다고", "잘했", "괜찮았", "인상적이었", "도움이 되었", "도움이 됐"

    ]


    # Closing: 요약 + 다음 단계, 주로 마지막 1~2문장
    closing_summary_patterns = [
        "정리하면", "요약하자면", "한마디로", "중요한 건"
    ]

    closing_next_patterns = [
        "다음엔", "다음에는", "다음에", "다음 단계",
        "해보자", "하면 좋겠어", "해보면 좋겠다"
    ]

    def match(text: str, patterns: list[str]) -> bool:
        return any(p in text for p in patterns)

    # ---- Opening 감지 ----
    has_opening = False
    for idx, sent in enumerate(sents):
        # 앞 2문장 안에서 "먼저/우선" + 질문성 패턴
        if idx <= 1 and match(sent, opening_first_patterns) and (
            "?" in sent or match(sent, opening_q_patterns)
        ):
            has_opening = True
            break

        # 전체 문장 중 "질문 + 전공의 생각/느낌/판단/설명" 패턴
        if "?" in sent and match(sent, opening_q_patterns):
            has_opening = True
            break

    # 완화: 질문만 있어도 Opening 인정, 또는 생각/설명 패턴만 있어도 인정
    if not has_opening:
        any_question = any("?" in s for s in sents)
        any_open_word = any(
            match(s, opening_q_patterns + opening_first_patterns) for s in sents
        )
        if any_question or any_open_word:
            has_opening = True

    # ---- Core 감지 ----
    has_core = False

      # ---- Core 감지 ----
    has_core = False

    # 1단계: 엄격한 기준 (관찰 + 결과/이유 세트)
    for idx, sent in enumerate(sents):
        # 한 문장 안에 관찰 + 결과/이유가 같이 있는 경우
        if match(sent, core_observation_patterns) and match(
            sent, core_reason_patterns
        ):
            has_core = True
            break

        # 관찰 문장 바로 다음 문장에서 결과/이유가 나오는 경우
        if match(sent, core_observation_patterns):
            if idx + 1 < len(sents) and match(sents[idx + 1], core_reason_patterns):
                has_core = True
                break

        # 관찰 + 긍정 평가(좋았어/잘했어 등)가 한 문장에 같이 있는 경우도 Core로 인정
        if match(sent, core_observation_patterns) and any(
            ev in sent for ev in evaluation_patterns
        ):
            has_core = True
            break

    # 2단계: 완화된 기준
    # - transcript 전체에서 관찰 패턴이 1번 이상
    # - 그리고 (결과/이유 패턴 OR 평가 패턴)이 1번 이상 있으면 Core로 인정
    if not has_core:
        any_observation = any(match(sent, core_observation_patterns) for sent in sents)
        any_reason = any(match(sent, core_reason_patterns) for sent in sents)
        any_eval = any(
            any(ev in sent for ev in evaluation_patterns) for sent in sents
        )
        if any_observation and (any_reason or any_eval):
            has_core = True


    # ---- Closing 감지 ----
    has_closing = False
    last_idx = len(sents) - 1
    for idx, sent in enumerate(sents):
        # 마지막 2문장 안에서 요약 또는 다음 단계 언급
        if idx >= last_idx - 1:
            if match(sent, closing_summary_patterns) or match(
                sent, closing_next_patterns
            ):
                has_closing = True
                break

    # 완화: 어디든 요약/다음 단계 패턴이 있으면 Closing 인정
    if not has_closing:
        any_closing_word = any(
            match(sent, closing_summary_patterns + closing_next_patterns)
            for sent in sents
        )
        if any_closing_word:
            has_closing = True
        else:
            # 마지막 문장이 '보자/해봐/해야/하도록 하자' 같은 제안/지시형이면 Closing으로 인정
            tail = sents[-1]
            if any(
                p in tail
                for p in ["보자", "해봐", "해보면", "해보는 게", "해야", "하도록 하자"]
            ):
                has_closing = True

    return {
        "has_opening": has_opening,
        "has_core": has_core,
        "has_closing": has_closing,
    }




# ==============================
#  아주 단순한 룰 기반 분석기 (MVP)
# ==============================
def _clamp_score(x: int, low: int = 1, high: int = 5) -> int:
    """OSAD 각 항목 점수를 1~5 범위로 제한"""
    return max(low, min(high, x))


def simple_osad_and_coach(transcript: str) -> tuple[OSADScores, Findings, CoachReport, dict]:
    t = transcript.strip()

    # 문장 구조 분석 (Opening / Core / Closing)
    structure = detect_structure(transcript)

    # 키워드 기반 요소 감지
    has_summary = any(k in t for k in ["요약", "정리하면", "핵심은", "한마디로"])
    has_next = any(k in t for k in ["다음엔", "다음에는", "계획은", "다음 단계", "다음 행동"])
    has_question = ("?" in t) or any(k in t for k in ["어땠", "생각은", "어떻게", "왜", "무엇이"])
    has_specificity = any(k in t for k in ["했을 때", "그래서", "그 결과", "때문에", "관찰"])

    # ---------------------------
    # OSAD 점수 계산 (1~5 스케일 정규화 버전)
    # ---------------------------
    s = OSADScores()

    # 1) 기본값: 2점을 “기본/보통” 수준으로 둠
    s.approach = 3  # 태도는 일단 중간 이상이라고 가정
    s.learning_env = 2
    s.engagement = 2
    s.reaction = 2
    s.reflection = 2
    s.analysis = 2
    s.diagnosis = 2
    s.application = 2
    s.summary = 2

    # 2) 질문/참여 (Engagement, Reflection, Learning environment)
    if has_question:
        s.engagement += 1
        s.reflection += 1
    if structure["has_opening"]:
        s.engagement += 1
        s.learning_env += 1

    # 3) 분석/핵심 내용 (Analysis, Diagnosis)
    if has_specificity:
        s.analysis += 1
    if structure["has_core"]:
        s.analysis += 1
        s.diagnosis += 1

    # 4) 요약/다음 단계 (Summary, Application)
    if has_summary:
        s.summary += 1
    if has_next:
        s.summary += 1
        s.application += 1
    if structure["has_closing"]:
        s.summary += 1
        s.application += 1

    # 5) 점수 범위를 1~5로 클램프
    s.approach = _clamp_score(s.approach)
    s.learning_env = _clamp_score(s.learning_env)
    s.engagement = _clamp_score(s.engagement)
    s.reaction = _clamp_score(s.reaction)
    s.reflection = _clamp_score(s.reflection)
    s.analysis = _clamp_score(s.analysis)
    s.diagnosis = _clamp_score(s.diagnosis)
    s.application = _clamp_score(s.application)
    s.summary = _clamp_score(s.summary)

    # 6) 총점 계산 (스케일 45 유지)
    s.total = sum(
        [
            s.approach,
            s.learning_env,
            s.engagement,
            s.reaction,
            s.reflection,
            s.analysis,
            s.diagnosis,
            s.application,
            s.summary,
        ]
    )

    # ---------------------------
    # 파생 지표
    # ---------------------------
    f = Findings(
        talk_listen_ratio="60:40" if has_question else "72:28",
        specific_examples=has_specificity,
        goal_setting=has_next,
    )

    # ---------------------------
    # 코칭 리포트 문구 생성 (OSAD 점수 반영 버전)
    # ---------------------------
    strengths: List[str] = []

    # ◆ 점수가 높은 영역을 강점으로 뽑기
    if s.engagement >= 4:
        strengths.append("전공의 참여(Engagement)를 잘 이끌어내고 있습니다.")
    if s.summary >= 4 and s.application >= 4:
        strengths.append("피드백의 요약과 다음 단계 제시(Summary/Application)가 비교적 잘 이루어집니다.")
    if s.analysis >= 4:
        strengths.append("상황 분석과 진단적 사고(Analysis/Diagnosis)가 피드백에 잘 드러납니다.")
    if s.learning_env >= 4:
        strengths.append("전반적으로 안전한 학습 환경(Learning environment)을 조성하려는 태도가 보입니다.")

    # 구조 기반 강점 (점수가 아주 높지는 않아도 구조가 있으면 칭찬)
    if not strengths:
        if has_question:
            strengths.append("전공의에게 질문을 던지며 대화를 이끌려는 시도가 있습니다.")
        if structure["has_opening"]:
            strengths.append("피드백 시작에서 전공의 생각을 먼저 묻는 시도가 있습니다.")
        if structure["has_closing"]:
            strengths.append("피드백 마무리에서 요약 또는 다음 단계를 언급하려는 노력이 보입니다.")

    if not strengths:
        strengths = ["친화적 접근(Approach)을 유지하고 있습니다."]

    # ◆ 개선점: 구조 + 점수 기반으로 추천
    improvements: List[str] = []

    # Opening 부족 / Engagement 낮음
    if s.engagement <= 3 or not structure["has_opening"]:
        improvements.append(
            "피드백 초반에 전공의의 생각을 1~2번 정도 먼저 물어보세요. "
            "예: '먼저 네 생각은 어땠어?' 같은 질문으로 대화를 열면 Engagement가 좋아집니다."
        )

    # Core 부족 / Analysis 낮음
    if s.analysis <= 3 or not structure["has_core"] or not has_specificity:
        improvements.append(
            "피드백 중간에 실제 관찰된 행동을 1개만이라도 구체적으로 언급해 보세요. "
            "예: '아까 X를 했을 때 Y가 좋아졌어.'처럼 관찰-영향을 연결하면 Analysis 점수가 올라갑니다."
        )

    # Closing 부족 / Summary/Application 낮음
    if s.summary <= 3 or s.application <= 3 or not structure["has_closing"]:
        improvements.append(
            "마무리 단계에서 오늘 이야기의 핵심과 다음 행동을 20초 안에 정리해 보세요. "
            "예: '정리하면 ○○가 중요했고, 다음엔 △△를 해보자.'와 같이 Summary/Application을 명시해 주세요."
        )

    # 질문 거의 없음 → Engagement/Reflection 보완
    if not has_question:
        improvements.append(
            "전공의에게 최소 2번 이상 '너는 어떻게 생각해?'와 같은 질문을 던져 참여와 자기성찰(Reflection)을 이끌어 보세요."
        )

    # 요약/다음 단계 각각에 대한 추가 보완
    if not has_summary:
        improvements.append(
            "피드백 끝에 '정리하면 ~'으로 시작하는 한 문장을 말해보는 연습을 해보면 Summary가 훨씬 또렷해집니다."
        )
    if not has_next:
        improvements.append(
            "다음 진료에서 시도해볼 행동을 1가지만 함께 정하고, 말로 확인해 주세요. "
            "예: '다음에는 처음 5분 안에 네 가설을 한 번 말해보자.'"
        )

    # 너무 길어지지 않게 상위 3개만
    coach = CoachReport(
        strengths=strengths[:2] or ["친화적 접근 유지"],
        improvements_top3=improvements[:3],
        script_next_time=(
            "“방금 네가 한 X는 ○○에 효과적이었어(관찰). "
            "그래서 △△가 좋아졌지(영향). "
            "다음엔 □□를 한번 시도해볼래?(대안)”"
        ),
        micro_habit_10sec="마무리 전에 '요약-다음-확인'을 머릿속으로 떠올리고 20초 안에 말로 정리해 보세요.",
    )

    return s, f, coach, structure



# ==============================
#  라우터 엔드포인트
# ==============================
@router.post("", response_model=FeedbackOut)
def create_feedback(payload: FeedbackIn) -> FeedbackOut:
    """
    지도전문의의 피드백 발화를 OSAD 관점에서 요약·코칭하는 엔드포인트
    """
    s, f, c, st = simple_osad_and_coach(payload.transcript)

    return FeedbackOut(
        encounter_id=payload.encounter_id,
        osad=s,
        findings=f,
        coach=c,
        structure=StructureReport(**st),
    )
