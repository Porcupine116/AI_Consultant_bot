from __future__ import annotations

from typing import Any

from storage.db import Database
from storage.models import ConversationRecord, LeadRecord, MessageRecord, UserRecord
from utils.helpers import utc_now_iso


class Repository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def ensure_user(self, user: UserRecord) -> None:
        now = utc_now_iso()
        async with self.db.connect() as conn:
            await conn.execute(
                """
                INSERT INTO users(chat_id, username, first_name, last_name, language_code, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    username=excluded.username,
                    first_name=excluded.first_name,
                    last_name=excluded.last_name,
                    language_code=excluded.language_code,
                    updated_at=excluded.updated_at
                """,
                (
                    user.chat_id,
                    user.username,
                    user.first_name,
                    user.last_name,
                    user.language_code,
                    now,
                    now,
                ),
            )
            await conn.commit()

    async def save_message(self, chat_id: int, role: str, content: str) -> None:
        async with self.db.connect() as conn:
            await conn.execute(
                "INSERT INTO messages(chat_id, role, content, created_at) VALUES(?,?,?,?)",
                (chat_id, role, content, utc_now_iso()),
            )
            await conn.commit()

    async def list_messages(self, chat_id: int, limit: int = 12) -> list[MessageRecord]:
        async with self.db.connect() as conn:
            rows = await conn.execute_fetchall(
                """
                SELECT role, content, created_at
                FROM messages
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat_id, limit),
            )
        items = [MessageRecord(role=row["role"], content=row["content"], created_at=row["created_at"]) for row in rows]
        return list(reversed(items))

    async def get_conversation(self, chat_id: int) -> ConversationRecord:
        async with self.db.connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM conversations WHERE chat_id = ?",
                (chat_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return ConversationRecord(chat_id=chat_id)
        return ConversationRecord(
            chat_id=row["chat_id"],
            state=row["state"],
            stage=row["stage"],
            handed_off=bool(row["handed_off"]),
            operator_requested=bool(row["operator_requested"]),
            context=self.db.loads(row["context_json"]),
            last_ai_reply=row["last_ai_reply"],
        )

    async def update_conversation(self, record: ConversationRecord) -> None:
        now = utc_now_iso()
        async with self.db.connect() as conn:
            await conn.execute(
                """
                INSERT INTO conversations(chat_id, state, stage, handed_off, operator_requested, context_json, last_ai_reply, updated_at)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    state=excluded.state,
                    stage=excluded.stage,
                    handed_off=excluded.handed_off,
                    operator_requested=excluded.operator_requested,
                    context_json=excluded.context_json,
                    last_ai_reply=excluded.last_ai_reply,
                    updated_at=excluded.updated_at
                """,
                (
                    record.chat_id,
                    record.state,
                    record.stage,
                    int(record.handed_off),
                    int(record.operator_requested),
                    self.db.dumps(record.context),
                    record.last_ai_reply,
                    now,
                ),
            )
            await conn.commit()

    async def set_handoff(self, chat_id: int, handed_off: bool = True, operator_requested: bool = False) -> ConversationRecord:
        record = await self.get_conversation(chat_id)
        record.handed_off = handed_off
        record.operator_requested = operator_requested
        if handed_off:
            record.state = "handoff"
            record.stage = "handoff"
        await self.update_conversation(record)
        return record

    async def merge_context(self, chat_id: int, updates: dict[str, Any]) -> ConversationRecord:
        record = await self.get_conversation(chat_id)
        for key, value in updates.items():
            if value not in (None, "", [], {}):
                record.context[key] = value
        await self.update_conversation(record)
        return record

    async def save_lead(self, lead: LeadRecord) -> None:
        now = utc_now_iso()
        async with self.db.connect() as conn:
            await conn.execute(
                """
                INSERT INTO leads(
                    chat_id, name, phone, telegram, region, accident_date, source, situation_summary, stage,
                    urgency, perspective, documents, next_step, ai_comment, status, handed_off,
                    operator_note, summary, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    name=excluded.name,
                    phone=excluded.phone,
                    telegram=excluded.telegram,
                    region=excluded.region,
                    accident_date=excluded.accident_date,
                    source=excluded.source,
                    situation_summary=excluded.situation_summary,
                    stage=excluded.stage,
                    urgency=excluded.urgency,
                    perspective=excluded.perspective,
                    documents=excluded.documents,
                    next_step=excluded.next_step,
                    ai_comment=excluded.ai_comment,
                    status=excluded.status,
                    handed_off=excluded.handed_off,
                    operator_note=excluded.operator_note,
                    summary=excluded.summary,
                    updated_at=excluded.updated_at
                """,
                (
                    lead.chat_id,
                    lead.name,
                    lead.phone,
                    lead.telegram,
                    lead.region,
                    lead.accident_date,
                    lead.source,
                    lead.situation_summary,
                    lead.stage,
                    lead.urgency,
                    lead.perspective,
                    lead.documents,
                    lead.next_step,
                    lead.ai_comment,
                    lead.status,
                    int(lead.handed_off),
                    lead.operator_note,
                    lead.summary,
                    lead.created_at or now,
                    lead.updated_at or now,
                ),
            )
            await conn.commit()

    async def get_lead(self, chat_id: int) -> LeadRecord | None:
        async with self.db.connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM leads WHERE chat_id = ?",
                (chat_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return LeadRecord(
            chat_id=row["chat_id"],
            name=row["name"],
            phone=row["phone"],
            telegram=row["telegram"],
            region=row["region"],
            accident_date=row["accident_date"],
            source=row["source"],
            situation_summary=row["situation_summary"],
            stage=row["stage"],
            urgency=row["urgency"],
            perspective=row["perspective"],
            documents=row["documents"],
            next_step=row["next_step"],
            ai_comment=row["ai_comment"],
            status=row["status"],
            handed_off=bool(row["handed_off"]),
            operator_note=row["operator_note"],
            summary=row["summary"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def list_recent_leads(self, limit: int = 10) -> list[LeadRecord]:
        async with self.db.connect() as conn:
            rows = await conn.execute_fetchall(
                "SELECT * FROM leads ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )
        return [
            LeadRecord(
                chat_id=row["chat_id"],
                name=row["name"],
                phone=row["phone"],
                telegram=row["telegram"],
                region=row["region"],
                accident_date=row["accident_date"],
                source=row["source"],
                situation_summary=row["situation_summary"],
                stage=row["stage"],
                urgency=row["urgency"],
                perspective=row["perspective"],
                documents=row["documents"],
                next_step=row["next_step"],
                ai_comment=row["ai_comment"],
                status=row["status"],
                handed_off=bool(row["handed_off"]),
                operator_note=row["operator_note"],
                summary=row["summary"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]
