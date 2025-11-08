# backend/api/feedback.py
import os, json
from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from openai import OpenAI

# 환경 변수 불러오기
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

router = APIRouter(prefix="/api", tags=["osad"])

# 요청/응답 스키마 정의
class FeedbackRequest(BaseModel):
    transcript: str = Field(..., description="지도전문의 피드백 전사 텍스트")
    trainee_level: str | None = Field(None, description="전공의 레벨 (PGY1/2/3 등)")
    language: str = Field("ko", description="ko 또는 en")

class DomainScore(BaseModel):
    score: int
    evidence: str
    suggestion: str

class FeedbackResponse(BaseModel):
    summary: str
    domains: Dict[str, DomainScore]
    overall: Dict[str, Any]

# OSAD 8도메인 평가 프롬프트
SYSTEM_PROMPT = """You are an expert medical educator evaluating faculty feedback using OSAD.
Evaluate strictly and return JSON only.
OSAD 8 domains:
1) Opening, 2) Structure, 3) Analysis, 4) Delivery, 5) Empathy, 6) Reflection, 7) Clarity, 8) Conciseness.
Scores: 1(poor)–5(excellent). Provide evidence (quote) and concrete suggestion for each domain.
If language='ko', respond in Korean; if 'en', respond in English.
Return JSON ONLY following the schema.
"""

USER_TMPL = """[CONTEXT]
- Trainee level: {level}
- Transcript (verbatim):
\"\"\"{transcript}\"\"\"

[TASK]
1) Summarize the feedback in 2~4 sentences.
2) Score OSAD 8 domains (1~5), each with 'evidence' (short quote) and 'suggestion' (1–2 lines).
3) Provide overall 'strengths'(bullets), 'improvements'(bullets), and 'action_plan'(3 bullet steps).

[OUTPUT JSON SCHEMA]
{{
  "summary": "...",
  "domains": {{
    "Opening":  {{ "score": 1, "evidence": "...", "suggestion": "..." }},
    "Structure":  {{ "score": 1, "evidence": "...", "suggestion": "..." }},
    "Analysis":  {{ "score": 1, "evidence": "...", "suggestion": "..." }},
    "Delivery":  {{ "score": 1, "evidence": "...", "suggestion": "..." }},
    "Empathy":  {{ "score": 1, "evidence": "...", "suggestion": "..." }},
    "Reflection":  {{ "score": 1, "evidence": "...", "suggestion": "..." }},
    "Clarity":  {{ "score": 1, "evidence": "...", "suggestion": "..." }},
    "Conciseness":  {{ "score": 1, "evidence": "...", "suggestion": "..." }}
  }},
  "overall": {{
    "strengths": ["...", "..."],
    "improvements": ["...", "..."],
    "action_plan": ["...", "...", "..."]
  }}
}}
"""

@router.post("/feedback", response_model=FeedbackResponse)
def analyze_feedback(req: FeedbackRequest):
    if not req.transcript or len(req.transcript.strip()) < 5:
        raise HTTPException(status_code=400, detail="transcript is too short")

    try:
        msgs = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TMPL.format(
                level=req.trainee_level or "unspecified",
                transcript=req.transcript.strip()
            ) + f"\n[LANG]\n{req.language}"}
        ]

        resp = client.chat.completions.create(
            model=MODEL,
            messages=msgs,
            temperature=0.3,
            response_format={"type": "json_object"},
            max_tokens=1200,
        )
        content = resp.choices[0].message.content
        data = json.loads(content)
        return JSONResponse(data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OSAD analysis failed: {e}")
