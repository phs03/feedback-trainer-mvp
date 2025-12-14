"""
backend.models 패키지

여기는 DB 테이블을 정의하는 SQLAlchemy 모델들을 모아두는 공간입니다.

현재 포함된 모델:
- DbHealthCheck : DB 연결 테스트용 모델
- CoachEval     : 코칭 리포트가 얼마나 도움이 되었는지 저장하는 테이블
- CoachMemo     : 코칭 리포트에서 사용자가 '기록' 체크한 항목을 저장하는 테이블
- Scenario      : 피드백/교육이 일어나는 상황(시뮬레이션, 임상 진료 등) 정의
- Scale         : 각 상황에서 사용하는 평가 스케일(OSAD, OMP 등)
- ScaleItem     : 스케일의 개별 문항 정의
"""

from .health_check import DbHealthCheck
from .feedback_models import CoachEval, CoachMemo
from .scale_models import Scenario, Scale, ScaleItem

__all__ = [
    "DbHealthCheck",
    "CoachEval",
    "CoachMemo",
    "Scenario",
    "Scale",
    "ScaleItem",
]
