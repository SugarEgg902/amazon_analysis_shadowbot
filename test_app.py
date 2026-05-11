from pathlib import Path
from threading import Event
from types import SimpleNamespace

import asyncio

from fastapi.testclient import TestClient

from app import ARTIFACTS_DIR, app, build_task_event_stream, create_app
from artifacts import ARTIFACTS_DIR as SHARED_ARTIFACTS_DIR


def _make_task(task_id="task-123", message="从亚马逊获取 Blackview 1 个竞品分析"):
    return SimpleNamespace(task_id=task_id, message=message, queue=asyncio.Queue())


def test_requirements_lists_fastapi_stack():
    text = Path("requirements.txt").read_text(encoding="utf-8")

    assert "fastapi" in text
    assert "uvicorn" in text
    assert "openai" in text


def test_create_chat_task_returns_task_id():
    client = TestClient(app)

    response = client.post("/api/chat", json={"message": "从亚马逊获取 Blackview 1 个竞品分析"})

    assert response.status_code == 200
    assert "task_id" in response.json()


def test_download_route_returns_404_for_missing_file():
    client = TestClient(app)

    response = client.get("/api/download/missing.csv")

    assert response.status_code == 404


def test_app_and_artifacts_share_same_absolute_artifacts_dir():
    assert ARTIFACTS_DIR == SHARED_ARTIFACTS_DIR
    assert ARTIFACTS_DIR.is_absolute()


def test_create_chat_task_schedules_run_task(monkeypatch):
    scheduled = {}
    called = Event()
    task = _make_task()

    def fake_new_task(message):
        task.message = message
        return task

    async def fake_run_task(message, queue):
        scheduled["message"] = message
        scheduled["queue"] = queue
        called.set()

    test_app = create_app(new_task_fn=fake_new_task, run_task_fn=fake_run_task)
    client = TestClient(test_app)
    response = client.post("/api/chat", json={"message": "从亚马逊获取 Blackview 1 个竞品分析"})

    assert response.status_code == 200
    assert response.json() == {"task_id": "task-123"}
    assert called.wait(1)
    assert scheduled == {
        "message": "从亚马逊获取 Blackview 1 个竞品分析",
        "queue": task.queue,
    }


def test_create_chat_task_streams_status_and_result_frames():
    tasks = {}
    message = "从亚马逊获取 Blackview 1 个竞品分析"

    def fake_new_task(request_message):
        task = _make_task(task_id="stream-happy", message=request_message)
        tasks[task.task_id] = task
        return task

    async def fake_run_task(_message, queue):
        await queue.put({"type": "status", "message": "working"})
        await queue.put({"type": "result", "summary": "done"})

    test_app = create_app(tasks=tasks, new_task_fn=fake_new_task, run_task_fn=fake_run_task)
    client = TestClient(test_app)

    create_response = client.post("/api/chat", json={"message": message})

    assert create_response.status_code == 200
    assert create_response.json() == {"task_id": "stream-happy"}
    task_id = create_response.json()["task_id"]

    response = client.get(f"/api/chat/{task_id}/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'data: {"type": "status", "message": "working"}\n\n' in response.text
    assert 'data: {"type": "result", "summary": "done"}\n\n' in response.text
    assert task_id not in tasks


def test_create_chat_task_streams_terminal_error_when_background_run_crashes():
    tasks = {}
    cleanup_scheduled = Event()
    task = _make_task(task_id="stream-background-error")

    def fake_new_task(_message):
        tasks[task.task_id] = task
        return task

    async def fake_run_task(_message, _queue):
        raise RuntimeError("worker exploded")

    def fake_cleanup_scheduler(task_id, task_map):
        assert task_id == task.task_id
        assert task_map is tasks
        cleanup_scheduled.set()

    test_app = create_app(
        tasks=tasks,
        new_task_fn=fake_new_task,
        run_task_fn=fake_run_task,
        cleanup_scheduler=fake_cleanup_scheduler,
    )
    client = TestClient(test_app)

    create_response = client.post("/api/chat", json={"message": task.message})

    assert create_response.status_code == 200
    assert cleanup_scheduled.wait(1)

    response = client.get(f"/api/chat/{task.task_id}/stream")

    assert response.status_code == 200
    assert 'data: {"type": "error", "message": "任务执行失败: worker exploded"}\n\n' in response.text


def test_create_chat_task_schedules_cleanup_after_background_completion_without_stream():
    tasks = {}
    cleanup_called = Event()
    task_finished = Event()
    task = _make_task(task_id="stream-no-consumer")

    def fake_new_task(_message):
        tasks[task.task_id] = task
        return task

    async def fake_run_task(_message, queue):
        await queue.put({"type": "result", "summary": "done"})
        task_finished.set()

    def fake_cleanup_scheduler(task_id, task_map):
        assert task_id == task.task_id
        assert task_map is tasks
        task_map.pop(task_id, None)
        cleanup_called.set()

    test_app = create_app(
        tasks=tasks,
        new_task_fn=fake_new_task,
        run_task_fn=fake_run_task,
        cleanup_scheduler=fake_cleanup_scheduler,
    )
    client = TestClient(test_app)

    create_response = client.post("/api/chat", json={"message": task.message})

    assert create_response.status_code == 200
    assert task_finished.wait(1)
    assert cleanup_called.wait(1)
    assert task.task_id not in tasks


def test_stream_route_emits_sse_frames_and_clears_terminal_task():
    task = _make_task(task_id="stream-terminal")
    tasks = {task.task_id: task}
    test_app = create_app(tasks=tasks)
    client = TestClient(test_app)

    asyncio.run(task.queue.put({"type": "status", "message": "working"}))
    asyncio.run(task.queue.put({"type": "result", "summary": "done"}))

    response = client.get(f"/api/chat/{task.task_id}/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'data: {"type": "status", "message": "working"}\n\n' in response.text
    assert 'data: {"type": "result", "summary": "done"}\n\n' in response.text
    assert task.task_id not in tasks


def test_stream_route_keeps_task_after_client_disconnect_before_terminal_event():
    task = _make_task(task_id="stream-disconnect")
    tasks = {task.task_id: task}
    asyncio.run(task.queue.put({"type": "status", "message": "working"}))
    stream = build_task_event_stream(task.task_id, task, tasks)
    chunk = asyncio.run(anext(stream))
    asyncio.run(stream.aclose())

    assert 'data: {"type": "status", "message": "working"}\n\n' == chunk
    assert task.task_id in tasks


def test_static_route_returns_404_when_frontend_directory_is_missing(tmp_path):
    missing_frontend = tmp_path / "frontend"
    test_app = create_app(frontend_dir=missing_frontend)
    client = TestClient(test_app)

    response = client.get("/static/app.js")

    assert response.status_code == 404


def test_frontend_files_exist():
    assert Path("frontend/index.html").exists()
    assert Path("frontend/app.js").exists()
    assert Path("frontend/styles.css").exists()
