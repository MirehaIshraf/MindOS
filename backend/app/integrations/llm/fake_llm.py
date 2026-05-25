from app.integrations.llm.base import LLMClient
from app.schemas.context import ContextPackage


class FakeLLMClient(LLMClient):
    def generate_response(
        self,
        message: str,
        history: list[dict],
        context,
        system_prompt: str | None = None,
    ) -> str:
        if isinstance(context, ContextPackage):
            return self._generate_from_package(context)

        if not context:
            return (
                "I don't have enough local information to answer that yet. Try seeding sample events from Developer "
                "Mode or connecting memory sources."
            )

        direct_events = [event for event in context if event.get("context_role", "direct") == "direct"]
        related_events = [event for event in context if event.get("context_role") == "related"]
        top_events = direct_events[:3] or context[:3]
        response_lines = [
            (
                "Based on direct matches and related memory, I found relevant context using keyword search."
                if related_events
                else "Based on your local memory, I found relevant context using keyword search."
            ),
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

        if related_events:
            response_lines.extend(["", "Related memory that helped:"])
            for event in related_events[:3]:
                response_lines.append(
                    f"- **{event['title']}** ({event['source']} / {event['type']}): {event['content_preview']}"
                )

        response_lines.append("")
        response_lines.append("I only used the direct and related local memory events listed as sources for this answer.")
        return "\n".join(response_lines)

    def _generate_from_package(self, context: ContextPackage) -> str:
        if not context.direct_events and not context.related_events:
            return (
                "I don't have enough local information to answer that yet. Try seeding sample events from Developer "
                "Mode or connecting memory sources."
            )

        response_lines = [
            (
                "I found direct matches and related memory in your local MindOS context."
                if context.related_events
                else "I found direct matches in your local MindOS context."
            ),
            "",
            context.summary,
            "",
            "Strongest signal:",
        ]

        for index, event in enumerate(context.direct_events[:3], start=1):
            response_lines.append(
                f"{index}. **{event.title}** ({event.source} / {event.type}): {event.content_preview}"
            )

        pattern = self._infer_pattern([event.model_dump() for event in context.direct_events[:3]])
        if pattern:
            response_lines.extend(["", pattern])

        if context.related_events:
            response_lines.extend(["", "Related memory that helped:"])
            for event in context.related_events[:3]:
                relationship = self._relationship_for_event(event.event_id, context)
                reason = f" via {relationship.relationship_type}: {relationship.reason}" if relationship else ""
                response_lines.append(f"- **{event.title}** ({event.source} / {event.type}){reason}")

        response_lines.append("")
        response_lines.append("I only used the structured local context and relationship reasons available in MindOS.")
        return "\n".join(response_lines)

    def _relationship_for_event(self, event_id: str, context: ContextPackage):
        for relationship in context.relationships:
            if relationship.from_event_id == event_id or relationship.to_event_id == event_id:
                return relationship
        return None

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
