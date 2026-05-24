from app.integrations.llm.base import LLMClient


class FakeLLMClient(LLMClient):
    def generate_response(
        self,
        message: str,
        history: list[dict],
        context: list[dict],
        system_prompt: str | None = None,
    ) -> str:
        if not context:
            return (
                "I don't have enough local information to answer that yet. Try seeding sample events from Developer "
                "Mode or connecting memory sources."
            )

        top_events = context[:3]
        response_lines = [
            "Based on your local memory, I found relevant context using keyword search.",
            "",
            "Top signals:",
        ]

        for index, event in enumerate(top_events, start=1):
            response_lines.append(
                f"{index}. **{event['title']}** ({event['source']} / {event['type']}): {event['content_preview']}"
            )

        pattern = self._infer_pattern(top_events)
        if pattern:
            response_lines.extend(["", pattern])

        response_lines.append("")
        response_lines.append("I only used the local memory events listed as sources for this answer.")
        return "\n".join(response_lines)

    def _infer_pattern(self, events: list[dict]) -> str | None:
        combined_text = " ".join(
            f"{event.get('title', '')} {event.get('content_preview', '')} {event.get('source', '')}" for event in events
        ).lower()

        if "deployment" in combined_text and ("jwt" in combined_text or "login" in combined_text or "auth" in combined_text):
            return (
                "The pattern points toward an authentication issue around deployment: local memory includes login "
                "failures, JWT/token errors, and related auth fixes."
            )
        if "error" in combined_text or "failed" in combined_text or "failure" in combined_text:
            return "The pattern points to a failure investigation with supporting events from your local memory."
        if "jira" in combined_text or "ticket" in combined_text:
            return "The pattern includes ticket-related work that may be useful for planning or follow-up."
        return None
