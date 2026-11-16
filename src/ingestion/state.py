from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from ..config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path         TEXT PRIMARY KEY,
    sha256       TEXT,
    library      TEXT,             -- public / private
    status       TEXT,             -- processing / processed / error / skipped
    chunk_count  INTEGER DEFAULT 0,
    doc_type     TEXT,
    tags         TEXT,             -- 完整标签 JSON
    error        TEXT,
    processed_at TEXT
);
"""

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()

def sha256_of(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def file_status(path: Path | str, sha: str) -> str | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT status, sha256 FROM files WHERE path = ?", (str(path),)
        ).fetchone()
        if row is None:
            return None
        if row["sha256"] == sha and row["status"] == "processed":
            return "processed"
        if row["sha256"] != sha:
            return "changed"
        return row["status"]
    finally:
        conn.close()

def get_sha(path: Path | str) -> str | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT sha256 FROM files WHERE path = ?", (str(path),)).fetchone()
        return row["sha256"] if row else None
    finally:
        conn.close()

def upsert(path: Path | str, sha: str, library: str, status: str, **fields) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO files (path, sha256, library, status, processed_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                sha256=excluded.sha256,
                library=excluded.library,
                status=excluded.status,
                processed_at=excluded.processed_at
            """,
            (str(path), sha, library, status, datetime.now().isoformat(timespec="seconds")),
        )
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            vals = list(fields.values())
            conn.execute(f"UPDATE files SET {sets} WHERE path=?", (*vals, str(path)))
        conn.commit()
    finally:
        conn.close()

def mark_processed(path: Path | str, sha: str, library: str, chunk_count: int, doc_type: str, tags: dict) -> None:
    upsert(path, sha, library, "processed", chunk_count=chunk_count, doc_type=doc_type, tags=json.dumps(tags, ensure_ascii=False), error="")

def mark_error(path: Path | str, sha: str, library: str, error: str) -> None:
    upsert(path, sha, library, "error", error=error[:500])

def mark_skipped(path: Path | str, sha: str, library: str) -> None:
    upsert(path, sha, library, "skipped", error="")

def list_files() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM files ORDER BY processed_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def count_by_library() -> dict[str, int]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT library, COUNT(*) AS n FROM files WHERE status='processed' GROUP BY library"
        ).fetchall()
        return {r["library"]: r["n"] for r in rows}
    finally:
        conn.close()

def clear_record(path: Path | str) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM files WHERE path = ?", (str(path),))
        conn.commit()
    finally:
        conn.close()
