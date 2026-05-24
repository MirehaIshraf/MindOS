from pathlib import Path

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import get_settings

Base = declarative_base()

_engine = None
_session_factory = None


class EventRecord(Base):
    __tablename__ = "events"

    id = Column(String, primary_key=True)
    source = Column(String, nullable=False, index=True)
    type = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    content = Column(Text, default="")
    metadata_json = Column(Text, default="{}")
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    embedding_status = Column(String, nullable=False)
    memory_category = Column(String, nullable=True, index=True)
    hidden_from_default = Column(Boolean, default=False, nullable=False)


class ChatSessionRecord(Base):
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, index=True)


class ChatMessageRecord(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    metadata_json = Column(Text, default="{}")
    sources_used_json = Column(Text, default="[]")
    model = Column(String, nullable=True)
    search_mode = Column(String, nullable=True)
    task_hint = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)


class TaskRecord(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True)
    task_type = Column(String, nullable=False, index=True)
    instruction = Column(Text, nullable=False)
    status = Column(String, nullable=False, index=True)
    preview_json = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)
    confirmation_token = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class PlaybookRecord(Base):
    __tablename__ = "playbooks"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    trigger_phrases_json = Column(Text, default="[]")
    steps_json = Column(Text, default="[]")
    run_count = Column(Integer, default=0, nullable=False)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


def get_database_path() -> Path:
    settings = get_settings()
    return Path(settings.sqlite_path)


def get_database_url() -> str:
    return f"sqlite:///{get_database_path().as_posix()}"


def get_engine():
    global _engine
    if _engine is None:
        database_path = get_database_path()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(get_database_url(), connect_args={"check_same_thread": False})
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False)
    return _session_factory


def initialize_database() -> None:
    Base.metadata.create_all(bind=get_engine())
