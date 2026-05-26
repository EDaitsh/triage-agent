import asyncio
import json
from typing import Optional

from backend.app.llm import structured_call
from backend.app.models import EvaluatorResult, RouterDecision, WorkerOutput
from backend.app.prompts import EVALUATOR_PROMPT, ROUTER_PROMPT, WORKER_PROMPT
from backend.app.store import create_task, get_task, update_task


async def run_workflow_cli(message: str):
    task_id = create_task({"message": message})
    print(f"[{task_id}] משימה נוצרה")
    await run_workflow(task_id, message)
    task = get_task(task_id)
    print(f"[{task_id}] הסתיים בסטטוס: {task.get('state')} – תוצאה: {task.get('final_output')}")


async def run_workflow(task_id: str, message: str):
    try:
        # 1. Router
        update_task(task_id, state="routing")
        router: RouterDecision = await structured_call(ROUTER_PROMPT, message, RouterDecision)
        update_task(task_id, router=router.model_dump())

        # 2. Worker + Evaluator (עד 2 ניסיונות)
        worker_output: Optional[WorkerOutput] = None
        evaluator: Optional[EvaluatorResult] = None

        for attempt in range(1, 3):
            update_task(task_id, state=f"working_attempt_{attempt}")
            worker_input = json.dumps(
                {
                    "message": message,
                    "router_decision": router.model_dump(),
                    "previous_feedback": evaluator.model_dump() if evaluator else None,
                },
                ensure_ascii=False,
            )
            worker_output = await structured_call(WORKER_PROMPT, worker_input, WorkerOutput)
            update_task(task_id, worker_output=worker_output.model_dump())

            update_task(task_id, state="evaluating")
            eval_input = json.dumps(
                {
                    "message": message,
                    "router_decision": router.model_dump(),
                    "worker_output": worker_output.model_dump(),
                },
                ensure_ascii=False,
            )
            evaluator = await structured_call(EVALUATOR_PROMPT, eval_input, EvaluatorResult)
            update_task(task_id, evaluator=evaluator.model_dump())

            if evaluator.passed:
                break

        # 3. HITL
        needs_hitl = (
            router.requires_human
            or router.category == "urgent_human"
            or not evaluator
            or not evaluator.passed
            or evaluator.needs_human
        )

        if needs_hitl:
            update_task(task_id, state="pending_approval", final_output=worker_output.model_dump() if worker_output else None)
            for _ in range(300):  # עד 5 דקות
                task = get_task(task_id)
                if task and task.get("state") in {"approved", "rejected"}:
                    break
                await asyncio.sleep(1)

            task = get_task(task_id)
            if task and task.get("state") == "rejected":
                return
            if task and task.get("approved_output"):
                worker_output = WorkerOutput(**task["approved_output"])

        # 4. סיום
        update_task(task_id, state="completed", final_output=worker_output.model_dump() if worker_output else None)

    except Exception as e:
        update_task(task_id, state="error", error=str(e))
