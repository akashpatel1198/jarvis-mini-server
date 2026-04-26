import os

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from openai import OpenAI

load_dotenv()

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = (
    "You are Jarvis, a personal voice assistant. "
    "Your replies are spoken aloud, so keep them concise — one or two sentences "
    "unless the question really requires more. "
    "Use plain spoken English: no bullet points, no markdown, no asterisks. "
    "If you don't know, say so briefly."
)

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
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty audio upload")

    transcript = _whisper_transcribe(
        audio.filename or "audio.m4a", data, audio.content_type
    )

    chat = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": transcript},
        ],
    )
    reply = chat.choices[0].message.content or ""
    return {"transcript": transcript, "reply": reply}
