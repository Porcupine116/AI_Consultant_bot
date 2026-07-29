from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from utils.helpers import ensure_parent_dir


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def init(self) -> None:
        ensure_parent_dir(self.path)
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    chat_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    chat_id INTEGER PRIMARY KEY,
                    state TEXT,
                    stage TEXT,
                    handed_off INTEGER NOT NULL DEFAULT 0,
                    operator_requested INTEGER NOT NULL DEFAULT 0,
                    context_json TEXT NOT NULL DEFAULT '{}',
                    last_ai_reply TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_chat_id_created_at
                ON messages(chat_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL UNIQUE,
                    name TEXT,
                    phone TEXT,
                    telegram TEXT,
                    region TEXT,
                    accident_date TEXT,
                    source TEXT,
                    situation_summary TEXT,
                    stage TEXT,
                    urgency TEXT,
                    perspective TEXT,
                    documents TEXT,
                    next_step TEXT,
                    ai_comment TEXT,
                    status TEXT NOT NULL DEFAULT 'new',
                    handed_off INTEGER NOT NULL DEFAULT 0,
                    operator_note TEXT,
                    summary TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_leads_status_updated_at
                ON leads(status, updated_at DESC);
                """
            )
            await conn.commit()

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        ensure_parent_dir(self.path)
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn

    @staticmethod
    def dumps(data: dict) -> str:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def loads(raw: str | None) -> dict:
        if not raw:
            return {}
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}
