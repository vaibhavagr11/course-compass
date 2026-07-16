from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.engine import v1_ask, v2_ask, consistency

app = FastAPI(title="Course Compass API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # fine for local dev
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskReq(BaseModel):
    question: str

class ConsReq(BaseModel):
    question: str
    runs: int = 5

@app.get("/api/health")
def health():
    return {"ok": True}

@app.post("/api/ask")
def ask(r: AskReq):
    return {"v1": v1_ask(r.question), "v2": v2_ask(r.question)}

@app.post("/api/consistency")
def cons(r: ConsReq):
    return {"v1": consistency(r.question, "v1", r.runs),
            "v2": consistency(r.question, "v2", r.runs)}