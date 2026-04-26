import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import os

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from openai import OpenAI

import tools

load_dotenv()

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = (
    "You are Jarvis, a personal voice assistant. "
    "Your replies are spoken aloud, so keep them concise — one or two sentences "
    "unless the question really requires more. "
    "Use plain spoken English: no bullet points, no markdown, no asterisks. "
    "If you don't know, say so briefly. "
    "When a tool is available for the user's request, use it instead of guessing."
)

LOG_FILE = Path("logs/requests.jsonl")
LOG_FILE.parent.mkdir(exist_ok=True)

app = FastAPI(title="jarvis-mini-server")
client = OpenAI()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _whisper_transcribe(
    filename: str, data: bytes, content_type: str | None
) -> str:
    result = client.audio.transcriptions.create(
        model=WHISPER_MODEL,
        file=(filename, data, content_type or "application/octet-stream"),
    )
    return result.text


def _log_request(entry: dict[str, Any]) -> None:
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> dict[str, str]:
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty audio upload")
    text = _whisper_transcribe(
        audio.filename or "audio.m4a", data, audio.content_type
    )
    return {"text": text}


@app.post("/command")
async def command(audio: UploadFile = File(...)) -> dict[str, str]:
    started = time.perf_counter()
    log_entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "transcript": None,
        "tool_called": None,
        "tool_args": None,
        "tool_result": None,
        "reply": None,
        "latency_ms": None,
        "error": None,
    }

    try:
        data = await audio.read()
        if not data:
            raise HTTPException(status_code=400, detail="empty audio upload")

        transcript = _whisper_transcribe(
            audio.filename or "audio.m4a", data, audio.content_type
        )
        log_entry["transcript"] = transcript

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": transcript},
        ]

        first = client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            tools=tools.all_definitions(),
        )
        first_msg = first.choices[0].message

        if first_msg.tool_calls:
            tool_call = first_msg.tool_calls[0]
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments or "{}")
            log_entry["tool_called"] = tool_name
            log_entry["tool_args"] = tool_args

            tool_result = tools.execute(tool_name, tool_args)
            log_entry["tool_result"] = tool_result

            messages.append(first_msg.model_dump())
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                }
            )
            second = client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
            )
            reply = second.choices[0].message.content or ""
        else:
            reply = first_msg.content or ""

        log_entry["reply"] = reply
        return {"transcript": transcript, "reply": reply}
    except HTTPException as e:
        log_entry["error"] = f"http_{e.status_code}: {e.detail}"
        raise
    except Exception as e:
        log_entry["error"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        log_entry["latency_ms"] = int((time.perf_counter() - started) * 1000)
        _log_request(log_entry)
