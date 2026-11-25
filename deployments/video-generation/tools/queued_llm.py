"""Spool OpenAI-compatible replies while the shared queue owns the GPU."""
import asyncio
from contextlib import suppress
import json
from pathlib import Path

import httpx

SUPPORTED_OPERATIONS = {"chat/completions", "completions", "responses"}
MAX_RESPONSE_BYTES = 128 * 1024**2


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False) + "\n")
    temporary.replace(path)


async def _execute(job, url, client):
    request = job["request"]
    folder = Path(job["directory"])
    body = request["body"]
    headers = {"X-Request-Id": job["id"]}
    async with client.stream("POST", url + "/v1/" + request["operation"], json=body, headers=headers) as response:
        streaming = response.is_success and response.headers.get("content-type", "").startswith("text/event-stream")
        filename = "response.sse" if streaming else "response.json"
        metadata = {"status_code": response.status_code, "stream": streaming, "filename": filename,
                    "content_type": response.headers.get("content-type", "application/json")}
        with (folder / filename).open("wb", buffering=0) as output:
            if streaming:
                atomic_json(folder / "response-meta.json", metadata)
            bytes_written = 0
            async for chunk in response.aiter_bytes():
                bytes_written += len(chunk)
                if bytes_written > MAX_RESPONSE_BYTES:
                    raise RuntimeError("The inference response exceeded the spool limit")
                output.write(chunk)
        if not streaming:
            atomic_json(folder / "response-meta.json", metadata)
            if response.is_server_error:
                detail = (folder / filename).read_bytes()[-8192:].lower()
                if b"out of memory" in detail:
                    raise MemoryError("Qwen inference ran out of memory")
        return response.status_code


async def execute_llm_job(store, job, backend_url, client, shutdown):
    task = asyncio.create_task(_execute(job, backend_url, client))
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=0.25)
            current = store.get(job["id"])
            if shutdown.is_set() or current["status"] == "cancelled":
                return
        code = task.result()
        status = "completed" if 200 <= code < 300 else "failed"
        folder = Path(job["directory"])
        if status == "completed":
            atomic_json(folder / "result-meta.json", {"status_code": code})
        store.change(job["id"], status, None if status == "completed" else f"Qwen returned HTTP {code}", only_running=True)
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
