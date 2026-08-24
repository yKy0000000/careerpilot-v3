import json

from sqlmodel import SQLModel, Field, create_engine, Session
from datetime import datetime, timezone
from pathlib import Path

class Analysis(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    jd_id: str
    reasoning: str
    matched_skills: str
    gaps: str
    iterations: int
    total_tokens: int
    created_at: str


DB_PATH = Path(__file__).resolve().parent.parent / "careerpilot.db"
engine = create_engine(f"sqlite:///{DB_PATH}")
SQLModel.metadata.create_all(engine)

def save_analysis(jd_id, result, iterations, total_tokens):
    try:
        with Session(engine) as session:
            row = Analysis(
                jd_id=jd_id,
                reasoning=result["reasoning"],
                matched_skills=json.dumps(result["matched_skills"]),
                gaps=json.dumps(result["gaps"]),
                iterations=iterations,
                total_tokens=total_tokens,
                created_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            )
            session.add(row)
            session.commit()
    except Exception as e:
        print(f"保存失败: {type(e).__name__}: {e}")