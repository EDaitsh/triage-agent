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
async def submit_message(body: MessageRequest, background_tasks: BackgroundTasks):
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
        raise HTTPException(status_code=400, detail="Task is not pending approval")
    update_task(task_id, state="approved", approved_output=body.approved_output)
    return {"status": "approved"}


@app.post("/tasks/{task_id}/reject")
async def reject_task(task_id: str, body: RejectRequest):
    """דחיית משימה בהמתנה."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("state") != "pending_approval":
        raise HTTPException(status_code=400, detail="Task is not pending approval")
    update_task(task_id, state="rejected", approval_comment=body.comment)
    return {"status": "rejected"}
