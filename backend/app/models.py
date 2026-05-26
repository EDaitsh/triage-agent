from pydantic import BaseModel


class RouterDecision(BaseModel):
    category: str
    requires_human: bool = False


class WorkerOutput(BaseModel):
    result: str
    missing_details: list[str] = []


class EvaluatorResult(BaseModel):
    passed: bool
    feedback: str = ""
    needs_human: bool = False

