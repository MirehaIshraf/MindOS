import re
from dataclasses import dataclass

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
]
ROOT_CAUSE_TERMS = ["why", "root cause", "caused", "cause", "failed", "failure", "error", "exception", "bug", "incident", "broke", "not working"]
SUMMARY_TERMS = ["summarize", "summary", "overview", "what did i work on", "report", "this week", "recent work"]
TASK_TERMS = ["create a jira", "jira ticket", "draft an email", "send an email", "create pr", "pull request", "commit message", "branch name"]
CODE_SOURCE_TERMS = ["vscode", "workspace", "editor", "file", "code", "repo", "repository", "commit", "branch"]
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
    def classify(self, query: str) -> QueryIntent:
        text = normalize(query)
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

        if any(term in text for term in ROOT_CAUSE_TERMS):
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

    def _is_memory_lookup(self, text: str) -> bool:
        if any(pattern in text for pattern in MEMORY_LOOKUP_PATTERNS) and any(term in text for term in ["search", "save", "saved", "find", "went through", "gone through", "visited", "doc", "page"]):
            return True
        return bool(re.search(r"\b(did|have|has).{0,30}\b(search|save|saved|visit|visited|open|opened)\b", text))


def normalize(value: str) -> str:
    return " ".join(value.lower().strip().replace("?", " ").split())


query_intent_service = QueryIntentService()
