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
async def command(audio: UploadFile = File(...)) -> dict[str, Any]:
    started = time.perf_counter()
    log_entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "transcript": None,
        "tool_calls": [],
        "phone_actions": [],
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
        phone_actions: list[dict[str, Any]] = []

        if first_msg.tool_calls:
            messages.append(first_msg.model_dump())
            for tool_call in first_msg.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments or "{}")
                try:
                    result = tools.execute(tool_name, tool_args)
                    text_for_llm = result.text
                    if result.phone_action is not None:
                        phone_actions.append(result.phone_action)
                except Exception as e:
                    text_for_llm = f"Tool error: {type(e).__name__}: {e}"

                log_entry["tool_calls"].append(
                    {"name": tool_name, "args": tool_args, "result": text_for_llm}
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": text_for_llm,
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
        log_entry["phone_actions"] = phone_actions
        return {
            "transcript": transcript,
            "reply": reply,
            "phone_actions": phone_actions,
        }
    except HTTPException as e:
        log_entry["error"] = f"http_{e.status_code}: {e.detail}"
        raise
    except Exception as e:
        log_entry["error"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        log_entry["latency_ms"] = int((time.perf_counter() - started) * 1000)
        _log_request(log_entry)
