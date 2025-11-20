# backend/api/db_test.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db import SessionLocal
from backend.models import DbHealthCheck

router = APIRouter(prefix="/debug", tags=["debug"])


def get_db():
    """
    요청마다 DB 세션 하나 열고, 끝나면 닫아주는 의존성
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/db-test")
def db_test(db: Session = Depends(get_db)):
    """
    - db_health_check 테이블에 한 줄 INSERT
    - commit 후 다시 읽어서 클라이언트에 반환
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
