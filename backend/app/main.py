import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

BACKEND_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"


@contextmanager
def database():
    path = Path(os.environ.get("DATABASE_PATH", str(BACKEND_DIR / "data" / "app.sqlite3")))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    with database() as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS notes ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL)"
        )
    yield


app = FastAPI(title="GhostTech API", lifespan=lifespan)


class NoteCreate(BaseModel):
    text: str = Field(min_length=1, max_length=1000)

    @field_validator("text", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class Note(NoteCreate):
    id: int


@app.get("/api/health")
def health():
    with database() as connection:
        connection.execute("SELECT 1")
    return {"status": "ok", "database": "sqlite"}


@app.get("/api/notes", response_model=list[Note])
def list_notes():
    with database() as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM notes ORDER BY id DESC")]


@app.post("/api/notes", response_model=Note, status_code=201)
def create_note(note: NoteCreate):
    with database() as connection:
        cursor = connection.execute("INSERT INTO notes (text) VALUES (?)", (note.text,))
        return {"id": cursor.lastrowid, "text": note.text}


@app.delete("/api/notes/{note_id}", status_code=204)
def delete_note(note_id: int):
    with database() as connection:
        cursor = connection.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Заметка не найдена")
    return Response(status_code=204)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
