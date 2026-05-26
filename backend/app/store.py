from typing import Optional


_tasks = {}
_task_counter = 0


def create_task(data: dict) -> str:
    global _task_counter
    _task_counter += 1
    task_id = f"task-{_task_counter}"
    _tasks[task_id] = {"state": "created", **data}
    return task_id


def update_task(task_id: str, **kwargs):
    if task_id in _tasks:
        _tasks[task_id].update(kwargs)


def get_task(task_id: str) -> Optional[dict]:
    return _tasks.get(task_id)