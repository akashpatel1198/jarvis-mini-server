import os

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from openai import OpenAI

load_dotenv()

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")

app = FastAPI(title="jarvis-mini-server")
client = OpenAI()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> dict[str, str]:
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty audio upload")

    # OpenAI's SDK reads the filename to infer format, so preserve it.
    filename = audio.filename or "audio.m4a"
    result = client.audio.transcriptions.create(
        model=WHISPER_MODEL,
        file=(filename, data, audio.content_type or "application/octet-stream"),
    )
    return {"text": result.text}
