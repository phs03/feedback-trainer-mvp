# backend/api/report.py
import os, io
from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

router = APIRouter(prefix="/api", tags=["report"])

# 입력 스키마 (FeedbackResponse 구조와 유사)
class DomainScore(BaseModel):
    score: int
    evidence: str
    suggestion: str

class ReportBody(BaseModel):
    summary: str
    domains: Dict[str, DomainScore]
    overall: Dict[str, Any]

def register_korean_font():
    # 윈도우 기본 폰트 (맑은 고딕) 등록
    try:
        font_path = r"C:\Windows\Fonts\malgun.ttf"
        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont("Malgun", font_path))
            return "Malgun"
    except Exception:
        pass
    return "Helvetica"  # 폴백 (영문 전용)

def wrap_text(text: str, width: int):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

@router.post("/report")
def generate_report(body: ReportBody):
    try:
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        width, height = A4
        font_name = register_korean_font()
        c.setFont(font_name, 12)

        y = height - 40
        c.setFont(font_name, 16)
        c.drawString(40, y, "OSAD Feedback Report")
        y -= 24

        # Summary
        c.setFont(font_name, 12)
        c.drawString(40, y, "Summary:")
        y -= 16
        c.setFont(font_name, 10)
        for line in wrap_text(body.summary, 90):
            c.drawString(50, y, line)
            y -= 14

        # Domains
        y -= 10
        c.setFont(font_name, 12)
        c.drawString(40, y, "OSAD Domains:")
        y -= 16
        c.setFont(font_name, 10)
        for name, ds in body.domains.items():
            c.drawString(45, y, f"- {name}: {ds.score}")
            y -= 14
            for line in wrap_text(f"evidence: {ds.evidence}", 92):
                c.drawString(55, y, line)
                y -= 12
            for line in wrap_text(f"suggestion: {ds.suggestion}", 92):
                c.drawString(55, y, line)
                y -= 12
            y -= 6
            if y < 80:
                c.showPage()
                y = height - 40
                c.setFont(font_name, 10)

        # Overall
        y -= 10
        c.setFont(font_name, 12)
        c.drawString(40, y, "Overall:")
        y -= 16
        c.setFont(font_name, 10)
        for key in ["strengths", "improvements", "action_plan"]:
            vals = body.overall.get(key, [])
            c.drawString(45, y, f"- {key}:")
            y -= 14
            for v in vals:
                for line in wrap_text(f"• {v}", 95):
                    c.drawString(55, y, line)
                    y -= 12
            y -= 4
            if y < 80:
                c.showPage()
                y = height - 40
                c.setFont(font_name, 10)

        c.showPage()
        c.save()
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=OSAD_Report.pdf"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")
