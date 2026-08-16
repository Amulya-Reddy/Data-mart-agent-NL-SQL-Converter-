"""FastAPI backend for the NCAP Data Mart Agent prototype."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend import agent, config, data_source

app = FastAPI(title="NCAP Data Mart Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in config.CORS_ALLOW_ORIGINS.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "data_source": data_source.active_source_name(),
        "mocked": not bool(config.ANTHROPIC_API_KEY),
    }


@app.post("/api/ask")
def ask(req: AskRequest):
    result = agent.ask(req.question)
    return {
        "answer": result["answer"],
        "queries": result["queries"],
        "mocked": result["mocked"],
        "data_source": data_source.active_source_name(),
    }
