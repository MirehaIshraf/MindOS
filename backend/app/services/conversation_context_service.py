from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.domain.models import ChatStoredMessage


FOLLOW_UP_PHRASES = [
    "this",
    "that",
    "it",
    "this model",
    "this patent",
    "this page",
    "this document",
    "this dataset",
    "this repo",
    "this issue",
    "this error",
    "the above",
    "previous one",
    "summarize it",
    "tell me more",
    "explain it",
    "what is it about",
    "give me a summary",
]


@dataclass
class ResolvedConversationContext:
    is_follow_up: bool = False
    resolved_query: str = ""
    primary_source_event_id: str | None = None
    primary_source_title: str | None = None
    primary_source_url: str | None = None
    source_event_ids: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    source_titles: list[str] = field(default_factory=list)
    reason: str = ""
    recent_history: list[dict[str, str]] = field(default_factory=list)
    topic: str | None = None

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        return {
            "is_follow_up": self.is_follow_up,
            "resolved_query": self.resolved_query,
            "primary_source_event_id": self.primary_source_event_id,
            "primary_source_title": self.primary_source_title,
            "primary_source_url": self.primary_source_url,
            "source_event_ids": self.source_event_ids,
            "entities": self.entities,
            "source_urls": self.source_urls,
            "source_titles": self.source_titles,
            "reason": self.reason,
            "recent_history": self.recent_history,
            "topic": self.topic,
        }


class ConversationContextService:
    def resolve_follow_up(
        self,
        *,
        query: str,
        recent_messages: list[ChatStoredMessage],
    ) -> ResolvedConversationContext:
        history = self._recent_history(recent_messages)
        previous = self._last_assistant_with_sources(recent_messages)
        if previous is None:
            return ResolvedConversationContext(is_follow_up=False, resolved_query=query, recent_history=history)

        metadata = previous.metadata or {}
        source_event_ids = self._string_list(metadata.get("source_event_ids"))
        source_urls = self._string_list(metadata.get("source_urls"))
        source_titles = self._string_list(metadata.get("source_titles"))
        entities = self._string_list(metadata.get("entities"))
        primary_source_event_id = self._string(metadata.get("primary_source_event_id"))

        if not self._is_follow_up_query(query) or not primary_source_event_id:
            return ResolvedConversationContext(
                is_follow_up=False,
                resolved_query=query,
                primary_source_event_id=primary_source_event_id,
                primary_source_title=self._string(metadata.get("primary_source_title")),
                primary_source_url=self._string(metadata.get("primary_source_url")),
                source_event_ids=source_event_ids,
                entities=entities,
                source_urls=source_urls,
                source_titles=source_titles,
                recent_history=history,
                topic=self._string(metadata.get("topic")),
            )

        entity = entities[0] if entities else self._string(metadata.get("primary_source_title")) or "the previous source"
        source_label = self._source_label(metadata)
        resolved_query = f"{query.strip()} about {entity} using the previously found {source_label}."
        return ResolvedConversationContext(
            is_follow_up=True,
            resolved_query=resolved_query,
            primary_source_event_id=primary_source_event_id,
            primary_source_title=self._string(metadata.get("primary_source_title")),
            primary_source_url=self._string(metadata.get("primary_source_url")),
            source_event_ids=source_event_ids or [primary_source_event_id],
            entities=entities,
            source_urls=source_urls,
            source_titles=source_titles,
            reason=f"User referred to the previous source with a follow-up phrase.",
            recent_history=history,
            topic=self._string(metadata.get("topic")) or entity,
        )

    def build_response_metadata(
        self,
        *,
        intent: str,
        resolved_query: str,
        user_query: str,
        sources: list[dict[str, Any]],
        conversation_context: ResolvedConversationContext,
    ) -> dict[str, Any]:
        source_event_ids = [str(source.get("event_id")) for source in sources if source.get("event_id")]
        source_urls = [str(source.get("url")) for source in sources if source.get("url")]
        source_titles = [str(source.get("title")) for source in sources if source.get("title")]
        primary = sources[0] if sources else {}
        entities = self.extract_entities(user_query, source_titles, source_urls)
        return {
            "intent": intent,
            "resolved_query": resolved_query,
            "entities": entities,
            "source_event_ids": source_event_ids,
            "source_urls": source_urls,
            "source_titles": source_titles,
            "primary_source_event_id": primary.get("event_id"),
            "primary_source_title": primary.get("title"),
            "primary_source_url": primary.get("url"),
            "topic": entities[0] if entities else (primary.get("title") or user_query[:80]),
            "is_follow_up": conversation_context.is_follow_up,
            "follow_up_reason": conversation_context.reason,
        }

    def extract_entities(self, query: str, titles: list[str], urls: list[str]) -> list[str]:
        candidates: list[str] = []
        for value in [*titles, query, *urls]:
            candidates.extend(self._entities_from_text(value))
        deduped: list[str] = []
        for candidate in candidates:
            cleaned = candidate.strip(" -_./")
            if len(cleaned) < 3:
                continue
            key = cleaned.lower()
            if key not in {item.lower() for item in deduped}:
                deduped.append(cleaned)
        return deduped[:8]

    def _is_follow_up_query(self, query: str) -> bool:
        text = " ".join(query.lower().split())
        if any(phrase in text for phrase in FOLLOW_UP_PHRASES):
            return True
        return len(text.split()) <= 5 and any(term in text for term in ["summary", "summarize", "explain", "details", "more"])

    def _last_assistant_with_sources(self, messages: list[ChatStoredMessage]) -> ChatStoredMessage | None:
        for message in reversed(messages):
            if message.role != "assistant":
                continue
            metadata = message.metadata or {}
            if metadata.get("primary_source_event_id") or metadata.get("source_event_ids") or message.sources_used:
                return message
        return None

    def _recent_history(self, messages: list[ChatStoredMessage], limit: int = 8) -> list[dict[str, str]]:
        return [
            {"role": message.role, "content": message.content}
            for message in messages[-limit:]
            if message.role in {"user", "assistant"} and message.content
        ]

    def _source_label(self, metadata: dict[str, Any]) -> str:
        title = self._string(metadata.get("primary_source_title")) or "memory source"
        url = self._string(metadata.get("primary_source_url"))
        if url and "huggingface.co" in url.lower():
            return "Hugging Face page"
        if "patent" in title.lower() or (url and "patents.google.com" in url.lower()):
            return "patent page"
        return "memory source"

    def _entities_from_text(self, value: str) -> list[str]:
        entities: list[str] = []
        entities.extend(re.findall(r"\b[A-Z]{1,5}\d{4,}[A-Z0-9-]*\b", value))
        entities.extend(re.findall(r"\b[A-Za-z0-9][A-Za-z0-9._-]+/[A-Za-z0-9][A-Za-z0-9._-]+\b", value))
        entities.extend(re.findall(r"\b[A-Za-z][A-Za-z0-9]*[A-Z][A-Za-z0-9-]*\b", value))
        if "hugging face" in value.lower():
            entities.append("Hugging Face")
        if "patent" in value.lower():
            entities.append("patent")
        return entities

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item]

    def _string(self, value: Any) -> str | None:
        return str(value) if isinstance(value, str) and value else None


conversation_context_service = ConversationContextService()
