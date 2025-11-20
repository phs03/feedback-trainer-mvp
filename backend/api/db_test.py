# backend/api/db_test.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import DbHealthCheck

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/db-test")
def db_test(db: Session = Depends(get_db)):
    """
    DB 연결 테스트용 엔드포인트.
    - db_health_check 테이블에 한 줄 insert 후, 그 내용을 바로 반환.
    """
    row = DbHealthCheck(note="ping from /debug/db-test")
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "id": row.id,
        "note": row.note,
        "created_at": row.created_at,
    }
