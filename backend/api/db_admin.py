# backend/api/db_admin.py

from typing import Dict, Any, List
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from backend.db import engine, get_db, SessionLocal
from backend.models.feedback_models import CoachEval, CoachMemo
from backend.models.health_check import DbHealthCheck
from backend.models import Scenario, Scale, ScaleItem  # ★ 새로 추가된 모델들

router = APIRouter(prefix="/db", tags=["db-admin"])


# ======================================================
# 1. DB 연결 정보
# ======================================================
@router.get("/info")
def db_info() -> Dict[str, Any]:
    """
    DB 연결 정보 및 엔진 상태 확인
    (기존 기능 유지)
    """
    url = str(engine.url)
    dialect = engine.url.get_dialect().name
    driver = engine.url.get_driver_name()

    return {
        "database_url": url,
        "dialect": dialect,
        "driver": driver,
        "status": "connected-ok",
    }


# ======================================================
# 2. 테이블 목록 조회
# ======================================================
@router.get("/tables")
def db_tables() -> Dict[str, Any]:
    """
    현재 DB에 생성된 테이블 목록 확인
    (기존 기능 유지)
    """
    insp = inspect(engine)
    tables = insp.get_table_names()

    return {
        "tables": tables,
        "count": len(tables),
    }


# ======================================================
# 3. 주요 테이블 샘플 조회
# ======================================================
@router.get("/sample")
def db_sample(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    주요 테이블 데이터 TOP 5 샘플 조회
    (기존 기능 유지)
    """
    result: Dict[str, Any] = {
        "coach_eval": [],
        "coach_memo": [],
        "db_health_check": [],
    }

    # CoachEval
    rows = db.query(CoachEval).limit(5).all()
    result["coach_eval"] = [
        {
            "id": r.id,
            "encounter_id": r.encounter_id,
            "scenario_code": r.scenario_code,
            "scale_code": r.scale_code,
            "model_version": r.model_version,
            "helpful_score": r.helpful_score,
            "helpful_flags": r.helpful_flags,
            "created_at": r.created_at,
        }
        for r in rows
    ]

    # CoachMemo
    rows = db.query(CoachMemo).limit(5).all()
    result["coach_memo"] = [
        {
            "id": r.id,
            "encounter_id": r.encounter_id,
            "scenario_code": r.scenario_code,
            "scale_code": r.scale_code,
            "model_version": r.model_version,
            "saved_sections": r.saved_sections,
            "created_at": r.created_at,
        }
        for r in rows
    ]

    # DbHealthCheck
    rows = db.query(DbHealthCheck).limit(5).all()
    result["db_health_check"] = [
        {
            "id": r.id,
            "message": r.message,
            "created_at": r.created_at,
        }
        for r in rows
    ]

    return result


# ======================================================
# 4. 스케일/시나리오 SEED를 위한 helper 함수들
# ======================================================
def _get_or_create_scenario(
    db: Session,
    code: str,
    name: str,
    description: str | None = None,
) -> Scenario:
    """
    Scenario(code=...) 가 있으면 그대로 반환,
    없으면 새로 만들고 flush 까지 수행.
    created_at NOT NULL 문제를 피하기 위해
    created_at 을 명시적으로 채워 넣는다.
    """
    obj = db.execute(
        select(Scenario).where(Scenario.code == code)
    ).scalar_one_or_none()
    if obj:
        return obj

    obj = Scenario(
        code=code,
        name=name,
        description=description,
        is_active=True,
        created_at=datetime.utcnow(),  # ★ NOT NULL 직접 채워주기
    )
    db.add(obj)
    db.flush()
    return obj


def _get_or_create_scale(
    db: Session,
    code: str,
    name: str,
    scenario: Scenario,
    description: str | None,
    max_item_score: int,
    num_items: int,
    max_total: int,
    version: str | None = None,
) -> Scale:
    """
    Scale(code=...) 이 있으면 그대로 반환,
    없으면 새로 만들고 flush 까지 수행.
    created_at NOT NULL 문제를 피하기 위해
    created_at 을 명시적으로 채워 넣는다.
    """
    obj = db.execute(
        select(Scale).where(Scale.code == code)
    ).scalar_one_or_none()
    if obj:
        return obj

    obj = Scale(
        code=code,
        name=name,
        description=description,
        scenario_id=scenario.id,
        max_item_score=max_item_score,
        num_items=num_items,
        max_total=max_total,
        version=version,
        is_active=True,
        created_at=datetime.utcnow(),  # ★ 안전하게 채워주기
    )
    db.add(obj)
    db.flush()
    return obj


def _create_scale_items_if_empty(
    db: Session,
    scale: Scale,
    items: List[Dict[str, Any]],
) -> int:
    """
    해당 scale에 이미 item이 있으면 아무 것도 만들지 않고 0 리턴.
    없으면 주어진 items 리스트를 생성하고 생성 개수를 리턴.
    created_at NOT NULL 문제를 피하기 위해 created_at 을 채워준다.
    """
    existing = db.execute(
        select(ScaleItem).where(ScaleItem.scale_id == scale.id)
    ).scalars().all()

    if existing:
        return 0

    count = 0
    for idx, item in enumerate(items, start=1):
        obj = ScaleItem(
            scale_id=scale.id,
            item_code=item["item_code"],
            order_index=item.get("order_index", idx),
            title_ko=item["title_ko"],
            title_en=item["title_en"],
            description_ko=item.get("description_ko"),
            description_en=item.get("description_en"),
            is_active=True,
            created_at=datetime.utcnow(),  # ★ 여기도
        )
        db.add(obj)
        count += 1

    return count


# ======================================================
# 5. OSAD / OMP 기본 스케일 SEED 엔드포인트
# ======================================================
@router.api_route("/seed-scales", methods=["GET", "POST"])
def seed_scales() -> Dict[str, Any]:
    """
    OSAD_DEBRIEFER, OMP_CLINICAL 스케일과 문항들을 기본값으로 삽입한다.
    여러 번 호출해도 중복 생성되지 않도록 설계함.
    GET / POST 둘 다 허용 (브라우저 주소창에서도 바로 호출 가능).
    """
    db = SessionLocal()

    try:
        # ---------- 1) OSAD: 시뮬레이션 디브리핑 ----------
        osad_scenario = _get_or_create_scenario(
            db,
            code="EM_DEBRIEF",
            name="응급의학 시뮬레이션 디브리핑 (Emergency Medicine Debriefing)",
            description="시뮬레이션 후 디브리핑 상황에서 사용하는 피드백 스케일.",
        )

        osad_scale = _get_or_create_scale(
            db,
            code="OSAD_DEBRIEFER",
            name="OSAD 스케일 (OSAD for Debriefer)",
            description="Objective Structured Assessment of Debriefing, 지도전문의/디브리퍼용 스케일.",
            scenario=osad_scenario,
            max_item_score=5,
            num_items=9,
            max_total=45,
            version="v1",
        )

        osad_items = [
            {
                "item_code": "OSAD_APPROACH",
                "title_ko": "접근과 분위기 설정 (Approach and environment)",
                "title_en": "Approach and environment",
            },
            {
                "item_code": "OSAD_LEARNING_ENV",
                "title_ko": "학습 환경 조성 (Establishing learning environment)",
                "title_en": "Establishing learning environment",
            },
            {
                "item_code": "OSAD_ENGAGEMENT",
                "title_ko": "참여와 의사소통 (Engagement and communication)",
                "title_en": "Engagement and communication",
            },
            {
                "item_code": "OSAD_REACTION",
                "title_ko": "반응 다루기 (Exploring reactions)",
                "title_en": "Exploring reactions",
            },
            {
                "item_code": "OSAD_REFLECTION",
                "title_ko": "성찰 유도 (Encouraging reflection)",
                "title_en": "Encouraging reflection",
            },
            {
                "item_code": "OSAD_ANALYSIS",
                "title_ko": "분석과 의미 부여 (Analysis and meaning making)",
                "title_en": "Analysis and meaning making",
            },
            {
                "item_code": "OSAD_DIAGNOSIS",
                "title_ko": "진단과 근거 토론 (Diagnosis and reasoning)",
                "title_en": "Diagnosis and reasoning",
            },
            {
                "item_code": "OSAD_APPLICATION",
                "title_ko": "임상 적용 논의 (Application to future practice)",
                "title_en": "Application to future practice",
            },
            {
                "item_code": "OSAD_SUMMARY",
                "title_ko": "요약과 마무리 (Summary and closure)",
                "title_en": "Summary and closure",
            },
        ]

        created_osad_items = _create_scale_items_if_empty(db, osad_scale, osad_items)

        # ---------- 2) OMP: 임상 진료 후 피드백 ----------
        omp_scenario = _get_or_create_scenario(
            db,
            code="CLINICAL_OMP",
            name="임상 진료 후 일상 피드백 (Clinical teaching with OMP)",
            description="환자를 진료한 전공의에게 일상적으로 제공하는 피드백 상황.",
        )

        omp_scale = _get_or_create_scale(
            db,
            code="OMP_CLINICAL",
            name="원 미닛 프리셉터 (One-Minute Preceptor)",
            description="One-Minute Preceptor 원형 스케일. 임상 진료 후 전공의 지도에 사용.",
            scenario=omp_scenario,
            max_item_score=5,
            num_items=5,
            max_total=25,
            version="v1",
        )

        # OMP 원형 5문항: 한글 제목 + (영어 병기)
        omp_items = [
            {
                "item_code": "OMP_COMMITMENT",
                "title_ko": "전공의에게 진단/계획을 말하게 하기 (Get a commitment)",
                "title_en": "Get a commitment",
            },
            {
                "item_code": "OMP_EVIDENCE",
                "title_ko": "근거와 사고 과정을 탐색하기 (Probe for supporting evidence)",
                "title_en": "Probe for supporting evidence",
            },
            {
                "item_code": "OMP_RULES",
                "title_ko": "일반적인 원칙을 가르치기 (Teach general rules)",
                "title_en": "Teach general rules",
            },
            {
                "item_code": "OMP_REINFORCE",
                "title_ko": "잘한 점을 구체적으로 강화하기 (Reinforce what was done right)",
                "title_en": "Reinforce what was done right",
            },
            {
                "item_code": "OMP_CORRECT",
                "title_ko": "개선이 필요한 부분을 교정하기 (Correct mistakes)",
                "title_en": "Correct mistakes",
            },
        ]

        created_omp_items = _create_scale_items_if_empty(db, omp_scale, omp_items)

        db.commit()

        return {
            "status": "ok",
            "message": "OSAD / OMP 기본 스케일 seed 완료",
            "details": {
                "osad": {
                    "scenario_code": osad_scenario.code,
                    "scale_code": osad_scale.code,
                    "items_created": created_osad_items,
                },
                "omp": {
                    "scenario_code": omp_scenario.code,
                    "scale_code": omp_scale.code,
                    "items_created": created_omp_items,
                },
            },
        }
    except Exception as e:
        db.rollback()
        print("=== DEBUG: /db/seed-scales ERROR ===", repr(e))
        return {
            "status": "error",
            "error": str(e),
        }
    finally:
        db.close()
