from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Index, Integer, String, Text, select, text, update
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import get_settings

settings = get_settings()
database_url = settings.database_url
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif database_url.startswith("postgresql://") and "+asyncpg" not in database_url:
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (Index("ix_conversation_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LongTermMemory(Base):
    __tablename__ = "long_term_memories"
    __table_args__ = (Index("ix_memory_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dimensions), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PendingConfirmation(Base):
    __tablename__ = "pending_confirmations"
    __table_args__ = (Index("ix_confirmation_user_status", "user_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


async def init_db() -> None:
    # pgvector must be available on the PostgreSQL server.
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def db_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def save_message(user_id: str, role: str, content: str) -> None:
    clean = content.strip()
    if not user_id or role not in {"user", "assistant"} or not clean:
        return
    async with db_session() as db:
        db.add(ConversationMessage(user_id=user_id, role=role, content=clean[:12000]))
        await db.commit()
    # Store user statements as semantic memory. Failure here never loses the transcript.
    if role == "user" and len(clean) >= 24:
        try:
            from .embeddings import embed_text
            vector = await embed_text(clean)
            if vector:
                async with db_session() as db:
                    db.add(LongTermMemory(user_id=user_id, content=clean[:4000], embedding=vector))
                    await db.commit()
        except Exception:
            pass


async def recall_memories(user_id: str, query: str, limit: int = 4) -> list[str]:
    if len(query.strip()) < 5:
        return []
    try:
        from .embeddings import embed_text
        vector = await embed_text(query)
        if not vector:
            return []
        async with db_session() as db:
            result = await db.execute(
                select(LongTermMemory.content)
                .where(LongTermMemory.user_id == user_id)
                .order_by(LongTermMemory.embedding.cosine_distance(vector))
                .limit(max(1, min(limit, 8)))
            )
            return [row[0] for row in result.all()]
    except Exception:
        return []


async def create_confirmation(user_id: str, action_type: str, payload: dict, ttl_seconds: int) -> str:
    from datetime import timedelta
    item = PendingConfirmation(
        user_id=user_id,
        action_type=action_type,
        payload=payload,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
    )
    async with db_session() as db:
        db.add(item)
        await db.commit()
    return str(item.id)


async def list_pending_confirmations(user_id: str) -> list[dict]:
    now = datetime.now(timezone.utc)
    async with db_session() as db:
        result = await db.execute(
            select(PendingConfirmation)
            .where(
                PendingConfirmation.user_id == user_id,
                PendingConfirmation.status == "pending",
                PendingConfirmation.expires_at > now,
            )
            .order_by(PendingConfirmation.created_at.desc())
            .limit(3)
        )
        rows = result.scalars().all()
        return [
            {"id": str(row.id), "action_type": row.action_type, "payload": row.payload,
             "created_at": row.created_at.isoformat(), "expires_at": row.expires_at.isoformat()}
            for row in rows
        ]


async def claim_confirmation(user_id: str, confirmation_id: str) -> dict | None:
    try:
        parsed_id = uuid.UUID(confirmation_id)
    except ValueError:
        return None
    now = datetime.now(timezone.utc)
    async with db_session() as db:
        result = await db.execute(
            update(PendingConfirmation)
            .where(
                PendingConfirmation.id == parsed_id,
                PendingConfirmation.user_id == user_id,
                PendingConfirmation.status == "pending",
                PendingConfirmation.expires_at > now,
            )
            .values(status="processing")
            .returning(PendingConfirmation.action_type, PendingConfirmation.payload)
        )
        claimed = result.first()
        await db.commit()
        if not claimed:
            return None
        return {"action_type": claimed[0], "payload": claimed[1]}


async def finish_confirmation(confirmation_id: str, status: str) -> None:
    try:
        parsed_id = uuid.UUID(confirmation_id)
    except ValueError:
        return
    async with db_session() as db:
        await db.execute(
            update(PendingConfirmation)
            .where(PendingConfirmation.id == parsed_id, PendingConfirmation.status == "processing")
            .values(status=status)
        )
        await db.commit()


async def reject_confirmation(user_id: str, confirmation_id: str) -> bool:
    try:
        parsed_id = uuid.UUID(confirmation_id)
    except ValueError:
        return False
    now = datetime.now(timezone.utc)
    async with db_session() as db:
        result = await db.execute(
            update(PendingConfirmation)
            .where(
                PendingConfirmation.id == parsed_id,
                PendingConfirmation.user_id == user_id,
                PendingConfirmation.status == "pending",
                PendingConfirmation.expires_at > now,
            )
            .values(status="rejected")
        )
        await db.commit()
        return bool(result.rowcount)
