from pathlib import Path

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, create_engine, inspect, text
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
    is_indexable = Column(Boolean, default=True, nullable=False)
    is_relationship_eligible = Column(Boolean, default=True, nullable=False)
    is_context_eligible = Column(Boolean, default=True, nullable=False)


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


class RelationshipRecord(Base):
    __tablename__ = "relationships"

    id = Column(String, primary_key=True)
    from_event_id = Column(String, nullable=False, index=True)
    to_event_id = Column(String, nullable=False, index=True)
    relationship_type = Column(String, nullable=False, index=True)
    strength = Column(Float, default=0.5, nullable=False)
    reason = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), nullable=False)


class AppSettingRecord(Base):
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class ConnectorSourceRecord(Base):
    __tablename__ = "connector_sources"

    id = Column(String, primary_key=True)
    connector_type = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    path = Column(Text, nullable=False, index=True)
    config_json = Column(Text, default="{}")
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    last_import_at = Column(DateTime(timezone=True), nullable=True)
    last_import_status = Column(String, nullable=True)
    last_import_message = Column(Text, nullable=True)


class ImportRunRecord(Base):
    __tablename__ = "import_runs"

    id = Column(String, primary_key=True)
    source_id = Column(String, nullable=True, index=True)
    connector_type = Column(String, nullable=False, index=True)
    path = Column(Text, nullable=False)
    status = Column(String, nullable=False)
    imported_count = Column(Integer, default=0, nullable=False)
    skipped_count = Column(Integer, default=0, nullable=False)
    failed_count = Column(Integer, default=0, nullable=False)
    message = Column(Text, default="")
    result_json = Column(Text, default="{}")
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=False)


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
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _ensure_event_policy_columns(engine)


def _ensure_event_policy_columns(engine) -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("events")}
    statements = []
    if "memory_category" not in columns:
        statements.append("ALTER TABLE events ADD COLUMN memory_category TEXT")
    if "hidden_from_default" not in columns:
        statements.append("ALTER TABLE events ADD COLUMN hidden_from_default BOOLEAN NOT NULL DEFAULT 0")
    if "is_indexable" not in columns:
        statements.append("ALTER TABLE events ADD COLUMN is_indexable BOOLEAN NOT NULL DEFAULT 1")
    if "is_relationship_eligible" not in columns:
        statements.append("ALTER TABLE events ADD COLUMN is_relationship_eligible BOOLEAN NOT NULL DEFAULT 1")
    if "is_context_eligible" not in columns:
        statements.append("ALTER TABLE events ADD COLUMN is_context_eligible BOOLEAN NOT NULL DEFAULT 1")

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        connection.execute(
            text(
                """
                UPDATE events
                SET memory_category = 'chat',
                    hidden_from_default = 1,
                    is_indexable = 0,
                    is_relationship_eligible = 0,
                    is_context_eligible = 0,
                    embedding_status = 'not_required'
                WHERE type IN ('chat_message', 'chat_response')
                """
            )
        )
        connection.execute(
            text(
                """
                UPDATE events
                SET memory_category = COALESCE(memory_category, 'captured_event'),
                    is_indexable = COALESCE(is_indexable, 1),
                    is_relationship_eligible = COALESCE(is_relationship_eligible, 1),
                    is_context_eligible = COALESCE(is_context_eligible, 1)
                WHERE type NOT IN ('chat_message', 'chat_response')
                """
            )
        )
