from fastapi import FastAPI

app = FastAPI(title="AI Feedback MVP", version="0.1.0")

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
