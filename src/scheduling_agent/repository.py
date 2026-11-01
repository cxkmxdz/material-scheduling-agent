"""Durable request idempotency and atomic slot rechecking inside SQLite transactions."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .schemas import Request, SLOT, dumps, utc


class RepositoryError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class Repository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS requests (
                    request_id TEXT PRIMARY KEY, digest TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS schedules (
                    schedule_id TEXT PRIMARY KEY, channel TEXT NOT NULL,
                    start TEXT NOT NULL, end TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS drafts (
                    draft_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL REFERENCES requests(request_id),
                    material_id TEXT NOT NULL, channel TEXT NOT NULL,
                    start TEXT NOT NULL, end TEXT NOT NULL,
                    reserves_slot INTEGER NOT NULL CHECK(reserves_slot IN (0,1)),
                    payload TEXT NOT NULL, UNIQUE(request_id,material_id));
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def register(self, request: Request):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT digest FROM requests WHERE request_id=?", (request.request_id,)).fetchone()
            if row and row["digest"] != request.digest():
                raise RepositoryError("REQUEST_ID_CONFLICT")
            db.execute("INSERT OR IGNORE INTO requests VALUES (?,?,?)",
                       (request.request_id, request.digest(), dumps(request.canonical())))

    def seed(self, schedules: list[dict]):
        with self.connection() as db:
            for s in schedules:
                start, end = datetime.fromisoformat(s["start"]), datetime.fromisoformat(s["end"])
                if start.tzinfo is None or end.tzinfo is None or end <= start:
                    raise ValueError("invalid seed schedule interval")
                db.execute("INSERT OR IGNORE INTO schedules VALUES (?,?,?,?)",
                           (s["schedule_id"], s["channel"], utc(start), utc(end)))

    @staticmethod
    def _conflicts(db, channel: str, start: datetime, end: datetime) -> list[dict]:
        # UTC fixed-width ISO strings; overlap iff a.start < b.end and a.end > b.start.
        rows = db.execute("""
            SELECT schedule_id AS id, start, end, 'confirmed_schedule' AS source FROM schedules
            WHERE channel=? AND start<? AND end>?
            UNION ALL
            SELECT draft_id AS id, start, end, 'reserved_draft' AS source FROM drafts
            WHERE channel=? AND reserves_slot=1 AND start<? AND end>?
        """, (channel, utc(end), utc(start), channel, utc(end), utc(start))).fetchall()
        return [dict(row) for row in rows]

    def conflicts(self, channel: str, start: datetime, end: datetime) -> list[dict]:
        with self.connection() as db:
            return self._conflicts(db, channel, start, end)

    def get_draft(self, request_id: str, material_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT payload FROM drafts WHERE request_id=? AND material_id=?",
                             (request_id, material_id)).fetchone()
            return json.loads(row["payload"]) if row else None

    def list_drafts(self) -> list[dict]:
        with self.connection() as db:
            return [json.loads(r["payload"]) for r in db.execute("SELECT payload FROM drafts ORDER BY rowid")]

    def save(self, request: Request, material_id: str, start: datetime, pending: bool,
             fail_after_insert: bool = False) -> tuple[dict, bool]:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT digest FROM requests WHERE request_id=?", (request.request_id,)).fetchone()
            if not row or row["digest"] != request.digest():
                raise RepositoryError("REQUEST_ID_CONFLICT")
            existing = db.execute("SELECT payload FROM drafts WHERE request_id=? AND material_id=?",
                                  (request.request_id, material_id)).fetchone()
            if existing:
                return json.loads(existing["payload"]), True
            if self._conflicts(db, request.channel, start, start + SLOT):
                raise RepositoryError("SLOT_CONFLICT")
            draft = {
                "draft_id": "draft-" + uuid4().hex, "request_id": request.request_id,
                "material_id": material_id, "channel": request.channel,
                "original_requirement": request.model_dump(mode="json"),
                "proposed_at": start.isoformat(), "end": (start + SLOT).isoformat(),
                "confirmation_status": "pending_confirmation" if pending else "not_required",
                "reserves_slot": not pending, "record_type": "draft", "published": False,
            }
            db.execute("INSERT INTO drafts (draft_id,request_id,material_id,channel,start,end,reserves_slot,payload) VALUES (?,?,?,?,?,?,?,?)",
                       (draft["draft_id"], request.request_id, material_id, request.channel,
                        utc(start), utc(start + SLOT), int(not pending), dumps(draft)))
            if fail_after_insert:
                # Real INSERT followed by a real SQLite error; context manager rolls back.
                db.execute("INSERT INTO injected_missing_table_for_save_failure VALUES (1)")
            return draft, False
