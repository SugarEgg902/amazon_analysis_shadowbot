from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent_service import TASKS, new_task, run_task
from artifacts import ARTIFACTS_DIR


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
TERMINAL_EVENT_TYPES = {"result", "error"}


class ChatRequest(BaseModel):
    message: str


class SafeStaticFiles(StaticFiles):
    async def check_config(self) -> None:
        if self.directory and not Path(self.directory).exists():
            return
        await super().check_config()

    async def get_response(self, path: str, scope):
        if self.directory and not Path(self.directory).exists():
            return Response(status_code=404)
        return await super().get_response(path, scope)


def build_task_event_stream(task_id: str, task, tasks: dict):
    async def event_stream():
        terminal_reached = False
        try:
            while True:
                payload = await task.queue.get()
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if payload.get("type") in TERMINAL_EVENT_TYPES:
                    terminal_reached = True
                    break
        finally:
            if terminal_reached:
                tasks.pop(task_id, None)

    return event_stream()


def schedule_task_cleanup(task_id: str, tasks: dict, delay_seconds: float = 60.0) -> None:
    async def cleanup():
        await asyncio.sleep(delay_seconds)
        tasks.pop(task_id, None)

    asyncio.create_task(cleanup())


async def run_task_with_cleanup(message: str, task, tasks: dict, run_task_fn, cleanup_scheduler) -> None:
    try:
        await run_task_fn(message, task.queue)
    except Exception as exc:
        await task.queue.put({"type": "error", "message": f"任务执行失败: {exc}"})
    finally:
        cleanup_scheduler(task.task_id, tasks)


def create_app(
    *,
    frontend_dir: Path = FRONTEND_DIR,
    artifacts_dir: Path = ARTIFACTS_DIR,
    tasks: dict = TASKS,
    new_task_fn=new_task,
    run_task_fn=run_task,
    cleanup_scheduler=schedule_task_cleanup,
):
    app = FastAPI()
    app.mount(
        "/static",
        SafeStaticFiles(directory=str(frontend_dir), html=True, check_dir=False),
        name="static",
    )

    @app.get("/")
    async def index():
        index_file = frontend_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return HTMLResponse("<html><body><h1>竞品分析</h1></body></html>")

    @app.post("/api/chat")
    async def create_chat(request: ChatRequest):
        task = new_task_fn(request.message)
        asyncio.create_task(
            run_task_with_cleanup(
                request.message,
                task,
                tasks,
                run_task_fn,
                cleanup_scheduler,
            )
        )
        return {"task_id": task.task_id}

    @app.get("/api/chat/{task_id}/stream")
    async def stream_chat(task_id: str):
        task = tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return StreamingResponse(
            build_task_event_stream(task_id, task, tasks),
            media_type="text/event-stream",
        )

    @app.get("/api/download/{filename}")
    async def download_file(filename: str):
        if Path(filename).name != filename:
            raise HTTPException(status_code=404, detail="File not found")

        path = artifacts_dir / filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        return FileResponse(path, filename=filename)

    return app


app = create_app()
