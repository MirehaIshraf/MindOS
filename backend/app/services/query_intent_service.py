import re
from dataclasses import dataclass

from typing import Any

from app.schemas.context import QueryIntent

MEMORY_LOOKUP_PATTERNS = [
    "did i",
    "have i",
    "ever",
    "did we",
    "have we",
    "search",
    "searched",
    "save",
    "saved",
    "find",
    "show me",
    "went through",
    "gone through",
    "go through",
    "looked at",
    "visited",
    "tell me about",
]
MEMORY_LOOKUP_TERMS = [
    "did i",
    "have i",
    "ever",
    "saved",
    "save",
    "searched",
    "search",
    "find",
    "show me",
    "went through",
    "gone through",
    "doc",
    "page",
    "link",
    "anything about",
    "tell me about",
    "tell me",
    "tell about",
]
ROOT_CAUSE_TERMS = [
    "root cause",
    "why failed",
    "why did it fail",
    "failed",
    "failure",
    "error",
    "exception",
    "crash",
    "bug",
    "not working",
    "broke",
    "deployment failed",
    "deployment fail",
    "login failed",
    "login fail",
    "issue caused by",
    "reason for failure",
]
GREETING_TERMS = {
    "hi",
    "hello",
    "hey",
    "assalamu alaikum",
    "salam",
    "good morning",
    "good afternoon",
    "good evening",
    "what's up",
    "whats up",
    "how are you",
    "thanks",
    "thank you",
    "okay",
    "ok",
    "cool",
}
SUMMARY_TERMS = ["summarize", "summary", "overview", "what did i work on", "report", "this week", "recent work"]
SOURCE_DETAIL_TERMS = [
    "give me details",
    "details of",
    "details about",
    "tell me about",
    "tell me more about",
    "summarize this",
    "summary about",
    "what is this model",
    "what is this dataset",
    "what is this patent",
    "what is this page",
]
SOURCE_ENTITY_TERMS = ["model", "dataset", "patent", "page", "document", "repo", "repository", "paper"]
TASK_TERMS = ["create a jira", "jira ticket", "draft an email", "send an email", "create pr", "create pull request", "commit message", "branch name"]
CODE_SOURCE_TERMS = ["vscode", "workspace", "editor", "file", "code", "repo", "repository", "commit", "branch"]
GITHUB_LOOKUP_TERMS = ["github", "pull request", "pull requests", "pr", "prs", "issue", "issues", "commit", "commits"]
STOP_WORDS = {
    "about",
    "anything",
    "before",
    "ever",
    "please",
    "that",
    "this",
    "the",
    "for",
    "with",
    "from",
    "into",
    "any",
    "some",
    "tell",
}
PRECISION_EXCLUDED_TYPES = [
    "editor_workspace_opened",
    "editor_file_opened",
    "heartbeat",
    "connector_status",
    "chat_message",
    "chat_response",
]


@dataclass(frozen=True)
class QueryIntentService:
    def classify(self, query: str, conversation_context: Any | None = None) -> QueryIntent:
        text = normalize(query)
        if getattr(conversation_context, "is_follow_up", False):
            return QueryIntent(
                intent="follow_up_summary" if self._is_summary_follow_up(text) else "follow_up",
                confidence=0.9,
                search_terms=getattr(conversation_context, "entities", []) or self.extract_search_terms(query),
                preferred_sources=[],
                excluded_types=list(PRECISION_EXCLUDED_TYPES),
                retrieval_profile="source_focused",
                needs_local_memory=True,
                allow_general_model_knowledge=False,
                answer_style="follow_up_summary" if self._is_summary_follow_up(text) else "memory_lookup",
            )
        if self._is_greeting_or_simple_chat(text):
            return QueryIntent(
                intent="general_chat",
                confidence=1.0,
                search_terms=[],
                preferred_sources=[],
                excluded_types=[],
                retrieval_profile="no_memory",
                needs_local_memory=False,
                allow_general_model_knowledge=True,
                answer_style="conversational",
            )
        if self._is_github_lookup(text):
            return QueryIntent(
                intent="memory_lookup",
                confidence=0.86,
                search_terms=self.extract_search_terms(query),
                preferred_sources=["github"],
                excluded_types=list(PRECISION_EXCLUDED_TYPES),
                retrieval_profile="precision_lookup",
                needs_local_memory=True,
                allow_general_model_knowledge=False,
                answer_style="memory_lookup",
            )

        task_hint = any(term in text for term in TASK_TERMS)
        if task_hint:
            return QueryIntent(
                intent="task_request",
                confidence=0.75,
                search_terms=self.extract_search_terms(query),
                preferred_sources=[],
                excluded_types=[],
                retrieval_profile="task",
                needs_local_memory=True,
                allow_general_model_knowledge=False,
                answer_style="task",
            )

        if self._is_memory_lookup(text):
            search_terms = self.extract_search_terms(query)
            preferred_sources = ["browser_extension", "file_system", "logs", "git"]
            excluded_types = list(PRECISION_EXCLUDED_TYPES)
            if any(term in text for term in CODE_SOURCE_TERMS):
                preferred_sources.append("vscode_extension")
            if "workspace" in text or "vscode" in text:
                excluded_types = [event_type for event_type in excluded_types if event_type != "editor_workspace_opened"]
            if "file" in text or "opened" in text or "open" in text:
                excluded_types = [event_type for event_type in excluded_types if event_type != "editor_file_opened"]
            return QueryIntent(
                intent="memory_lookup",
                confidence=0.82,
                search_terms=search_terms,
                preferred_sources=preferred_sources,
                excluded_types=excluded_types,
                retrieval_profile="precision_lookup",
                needs_local_memory=True,
                allow_general_model_knowledge=False,
                answer_style="memory_lookup",
            )

        if self._is_source_detail_query(text):
            return QueryIntent(
                intent="entity_details",
                confidence=0.84,
                search_terms=self.extract_entity_detail_terms(query),
                preferred_sources=["browser_extension"],
                excluded_types=list(PRECISION_EXCLUDED_TYPES),
                retrieval_profile="precision_lookup",
                needs_local_memory=True,
                allow_general_model_knowledge=False,
                answer_style="source_summary",
            )

        if self._is_root_cause(text):
            return QueryIntent(
                intent="root_cause",
                confidence=0.72,
                search_terms=self.extract_search_terms(query),
                preferred_sources=["logs", "git", "file_system", "browser_extension", "vscode_extension"],
                excluded_types=["chat_message", "chat_response", "editor_file_opened"],
                relationship_types_allowed=["FIXED_BY", "CAUSED_BY", "SAME_FILE", "SAME_TASK", "MENTIONS"],
                retrieval_profile="root_cause",
                needs_local_memory=True,
                allow_general_model_knowledge=False,
                answer_style="root_cause",
            )

        if any(term in text for term in SUMMARY_TERMS):
            return QueryIntent(
                intent="summary",
                confidence=0.68,
                search_terms=self.extract_search_terms(query),
                preferred_sources=[],
                excluded_types=["chat_message", "chat_response"],
                retrieval_profile="summary",
                needs_local_memory=True,
                allow_general_model_knowledge=False,
                answer_style="summary",
            )

        return QueryIntent(
            intent="general_chat",
            confidence=0.6,
            search_terms=self.extract_search_terms(query),
            preferred_sources=[],
            excluded_types=["chat_message", "chat_response", "editor_file_opened", "editor_workspace_opened"],
            retrieval_profile="general_chat",
            needs_local_memory=False,
            allow_general_model_knowledge=True,
            answer_style="normal",
        )

    def extract_search_terms(self, query: str) -> list[str]:
        text = normalize(query)
        text = re.sub(r"\b(did|have|has|do|does|can|could|would|please|me|i|we|you)\b", " ", text)
        for phrase in MEMORY_LOOKUP_TERMS:
            text = text.replace(phrase, " ")
        text = re.sub(r"\b(about|anything|ever|before|for|a|an|the|my|our)\b", " ", text)
        words = [word for word in re.findall(r"[a-z0-9+#._-]+", text) if len(word) > 1 and word not in STOP_WORDS]
        if not words:
            return [query.strip()]
        phrase = " ".join(words)
        terms = [phrase]
        if len(words) > 1:
            terms.extend(words)
            for index in range(len(words) - 1):
                terms.append(f"{words[index]} {words[index + 1]}")
        deduped: list[str] = []
        for term in terms:
            if term and term not in deduped:
                deduped.append(term)
        return deduped[:6]

    def extract_entity_detail_terms(self, query: str) -> list[str]:
        explicit = re.findall(r"\b[A-Za-z0-9][A-Za-z0-9._/-]*[A-Z0-9][A-Za-z0-9._/-]*\b", query)
        cleaned = self.extract_search_terms(query)
        terms: list[str] = []
        for term in explicit + cleaned:
            normalized_term = term.strip(" ?.,")
            if normalized_term and normalized_term.lower() not in {"give", "details", "model", "dataset", "patent", "page"}:
                if normalized_term not in terms:
                    terms.append(normalized_term)
        return terms[:6] or [query.strip()]

    def _is_memory_lookup(self, text: str) -> bool:
        if re.search(r"\btell me about\s+[a-z0-9+#._-]{3,}", text):
            return True
        if any(pattern in text for pattern in MEMORY_LOOKUP_PATTERNS) and any(term in text for term in ["search", "save", "saved", "find", "went through", "gone through", "visited", "doc", "page"]):
            return True
        return bool(re.search(r"\b(did|have|has).{0,30}\b(search|save|saved|visit|visited|open|opened)\b", text))

    def _is_summary_follow_up(self, text: str) -> bool:
        return any(term in text for term in ["summary", "summarize", "what is it about", "tell me more", "explain", "details"])

    def _is_source_detail_query(self, text: str) -> bool:
        if not any(term in text for term in SOURCE_DETAIL_TERMS):
            return False
        return any(term in text for term in SOURCE_ENTITY_TERMS) or bool(re.search(r"\b[a-z]+[a-z0-9._/-]*\d+[a-z0-9._/-]*\b", text))

    def _is_root_cause(self, text: str) -> bool:
        return any(term in text for term in ROOT_CAUSE_TERMS) or bool(re.search(r"\bwhy\b.{0,40}\bfail(?:ed|ure)?\b", text))

    def _is_greeting_or_simple_chat(self, text: str) -> bool:
        if text in GREETING_TERMS:
            return True
        if len(text.split()) <= 3 and not self._has_strong_local_intent(text):
            return True
        return False

    def _has_strong_local_intent(self, text: str) -> bool:
        if any(term in text for term in ROOT_CAUSE_TERMS):
            return True
        if re.search(r"\bwhy\b.{0,40}\bfail(?:ed|ure)?\b", text):
            return True
        if any(term in text for term in TASK_TERMS):
            return True
        return bool(re.search(r"\b(did|have|has).{0,30}\b(search|save|saved|visit|visited|open|opened)\b", text))

    def _is_github_lookup(self, text: str) -> bool:
        if not any(term in text for term in GITHUB_LOOKUP_TERMS):
            return False
        if "github" in text:
            return True
        return any(term in text for term in ["what", "show", "summarize", "recent", "open", "active", "did i", "have i"])


def normalize(value: str) -> str:
    return " ".join(value.lower().strip().replace("?", " ").split())


query_intent_service = QueryIntentService()
