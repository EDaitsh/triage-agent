from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .store import create_task, get_task, update_task
from .workflow import run_workflow

# ---------- FastAPI ----------
app = FastAPI(title="Triage Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Schemas לקלט ----------
class MessageRequest(BaseModel):
    message: str


class ApproveRequest(BaseModel):
    approved_output: Optional[dict] = None


class RejectRequest(BaseModel):
    comment: str = ""


# ---------- Endpoints ----------
@app.post("/message", status_code=202)
async def submit_message(
    body: MessageRequest, background_tasks: BackgroundTasks
):
    """שליחת הודעה חדשה – מחזיר task_id מיד."""
    task_id = create_task({"message": body.message})
    background_tasks.add_task(run_workflow, task_id, body.message)
    return {"task_id": task_id}


@app.get("/tasks/{task_id}")
async def get_task_endpoint(task_id: str):
    """קבלת מצב נוכחי של משימה."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.post("/tasks/{task_id}/approve")
async def approve_task(task_id: str, body: ApproveRequest):
    """אישור אנושי של משימה בהמתנה."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("state") != "pending_approval":
        raise HTTPException(
            status_code=400, detail="Task is not pending approval"
        )
    update_task(
        task_id, state="approved", approved_output=body.approved_output
    )
    return {"status": "approved"}


@app.post("/tasks/{task_id}/reject")
async def reject_task(task_id: str, body: RejectRequest):
    """דחיית משימה בהמתנה."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("state") != "pending_approval":
        raise HTTPException(
            status_code=400, detail="Task is not pending approval"
        )
    update_task(task_id, state="rejected", approval_comment=body.comment)
    return {"status": "rejected"}


# ── RAG Schemas ──────────────────────────────────────────────────────────────
class IngestRequest(BaseModel):
    text: str
    source: str = "manual"


class QueryRequest(BaseModel):
    question: str


class EvalsRequest(BaseModel):
    text: str
    n_questions: int = 5
    source: str = "eval_doc"


# ── RAG Endpoints ────────────────────────────────────────────────────────────
@app.post("/rag/ingest", status_code=201)
async def rag_ingest(body: IngestRequest):
    """הכנסת מסמך טקסט למאגר הידע הווקטורי."""
    from .rag import ingest_data
    n_chunks = await ingest_data(body.text, source=body.source)
    return {
        "status": "ingested",
        "chunks_added": n_chunks,
        "source": body.source,
    }


@app.post("/rag/query")
async def rag_query(body: QueryRequest):
    """שאילתת RAG – החזרת תשובה מבוססת מאגר ידע."""
    from .rag import answer_question
    result = await answer_question(body.question)
    return result


@app.get("/rag/status")
async def rag_status():
    """סטטיסטיקות מאגר הידע."""
    from .rag import get_collection_stats
    import asyncio
    stats = await asyncio.to_thread(get_collection_stats)
    return stats


@app.delete("/rag/clear", status_code=200)
async def rag_clear():
    """מחיקת כל ה-chunks מהמאגר (לאיפוס לפני ingestion מחדש)."""
    import asyncio
    import chromadb as _chromadb
    from .rag import CHROMA_PATH, COLLECTION_NAME

    def _clear():
        client = _chromadb.PersistentClient(path=CHROMA_PATH)
        client.delete_collection(COLLECTION_NAME)
        client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        return {"status": "cleared"}

    return await asyncio.to_thread(_clear)


@app.post("/rag/evals")
async def rag_evals(body: EvalsRequest, background_tasks: BackgroundTasks):
    """
    הפעלת pipeline הערכה:
    ingest → יצירת שאלות → RAG → ניקוד LLM.
    מחזיר תוצאות מלאות (עשוי לקחת מספר שניות).
    """
    from .rag_evals import run_evals
    results = await run_evals(
        body.text, n_questions=body.n_questions, source=body.source
    )
    return results
