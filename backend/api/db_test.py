# backend/api/db_test.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db import SessionLocal, engine
from backend.models import DbHealthCheck

router = APIRouter(prefix="/debug", tags=["debug"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/db-test")
def db_test(db: Session = Depends(get_db)):
    # 1) 헬스체크 레코드 하나 INSERT
    row = DbHealthCheck(note="ping from /debug/db-test")
    db.add(row)
    db.commit()
    db.refresh(row)

    # 2) 현재 어떤 DB URL을 쓰는지도 같이 보여주기
    return {
        "ok": True,
        "id": row.id,
        "note": row.note,
        "created_at": row.created_at,
        "db_url": str(engine.url),
    }
