"""MCP Tool Router Service — bridges LLM tool-calling to MCP client.

When the LLM generates a response that includes tool calls (function-calling),
this service:
1. Parses the tool calls from the LLM response
2. Routes each call to the MCP client
3. Collects results and feeds them back to the LLM
4. Handles confirmation gates for side-effect operations

The LLM is never allowed to execute side-effect tools directly.
Read-only tools are executed immediately and results are returned.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.integrations.mcp.client import mcp_client
from app.integrations.mcp.gmail_server import gmail_mcp_server
from app.integrations.mcp.protocol import McpToolCallResult
from app.schemas.gmail import GmailDraftPrepareRequest
from app.schemas.mcp import McpChatToolCall, McpChatToolResult
from app.services.file_index_service import file_index_service
from app.services.gmail_draft_planner import gmail_draft_planner
from app.services.gmail_service import gmail_service
from app.services.model_router_service import model_router_service

# ---------------------------------------------------------------------------
# MCP-aware system prompt addition
# ---------------------------------------------------------------------------

MCP_SYSTEM_PROMPT_FRAGMENT = """

When the user asks you to organize, manage, scan, or query files and folders, you have access to MCP file system tools. Use them as follows:

1. For scanning a folder: call `fs.scan_folder` with the root_path.
2. For listing file categories: call `fs.list_categories`.
3. For generating an organize plan: call `fs.organize_plan` with the root_path and instruction.
4. For checking if a file exists: call `fs.file_exists`.
5. For getting a folder summary: call `fs.folder_summary`.
6. For document questions/summaries: call `fs.search_files` first, then `fs.read_file` or `fs.summarize_file`.
7. If there is no indexed document match yet, call `fs.index_folder` for the configured root, then search again.

Rules:
- Always scan or summarize first before proposing any file operations.
- Never create folders or move files without first showing the user a plan from `fs.organize_plan`.
- Side-effect operations (create_folder, move_file) require user confirmation. If the tool returns `requires_confirmation: true`, tell the user what will happen and ask them to confirm.
- If a tool returns an error, explain the error to the user clearly.
- If an MCP server is disabled, tell the user to enable it in Connectors.
- Do not invent file paths or folder contents. Only report what the tools return.
- When answering from a document, mention which file you selected if the user did not name an exact file.

For email tasks, you also have Gmail tools:
1. To list/summarize recent emails: call `gmail.recent_emails`.
2. To preview a draft (and find a connected file to attach): call `gmail.prepare_draft` with `to`, `subject`, `body`, and optional `attachment_query` (e.g. "resume").
3. To create the draft: call `gmail.create_draft` with `to`, `subject`, `body`, and `indexed_attachments` (from prepare_draft).
4. To send the email: call `gmail.send_email` with the same arguments.

Multi-step + Gmail rules:
- For multi-step requests, run read-only tools first (e.g. scan/summarize a folder, or `gmail.prepare_draft`), then the side-effect tool.
- Compose the full draft yourself (to, subject, body) from the user's request and any memory context.
- Always call `gmail.prepare_draft` first so the user can review; never claim an email was drafted or sent until a confirmed tool result says so.
- Attachments must come from connected indexed files — use the `indexed_attachments` references returned by `gmail.prepare_draft`. Never invent file paths.
- `gmail.create_draft` and `gmail.send_email` require user confirmation.
- If Gmail is not connected, tell the user to connect it in Connectors.
- Do NOT expose raw tool names (like `gmail.create_draft`) in your final answer to the user — speak naturally.

IMPORTANT: To use ANY tool (file system or Gmail), you MUST output a JSON block in this exact format:
```json
{"name": "<tool_name>", "arguments": { ... }}
```
Examples:
```json
{"name": "fs.scan_folder", "arguments": {"root_path": "PATH_HERE"}}
```
```json
{"name": "gmail.create_draft", "arguments": {"to": "a@b.com", "subject": "Hello", "body": "Hi there"}}
```
For file tools: if the user mentions a path, use it; otherwise use the configured root_path. Always output a tool call JSON block when the user asks about files/folders or email — do NOT just describe what you would do; actually output the tool call.
"""


# ---------------------------------------------------------------------------
# Tool call parsing from LLM responses
# ---------------------------------------------------------------------------

def parse_tool_calls_from_llm_response(response_text: str) -> list[McpChatToolCall]:
    """Parse tool calls from an LLM response that uses function-calling format.

    Supports two formats:
    1. OpenAI-style: ```json\n{"name": "fs.scan_folder", "arguments": {...}}\n```
    2. Simple format: Action: fs.scan_folder(root_path="D:\\Downloads")

    Returns a list of parsed tool calls.
    """
    calls: list[McpChatToolCall] = []

    # Try OpenAI function-calling JSON format
    json_pattern = re.compile(r'```json\s*(\{.*?\})\s*```', re.DOTALL)
    for match in json_pattern.finditer(response_text):
        try:
            data = json.loads(match.group(1))
            name = data.get("name", "")
            arguments = data.get("arguments", {})
            if name:
                calls.append(McpChatToolCall(tool_name=name, arguments=arguments))
        except json.JSONDecodeError:
            continue

    # Try action format: tool_name(key="value", key2="value2")
    action_pattern = re.compile(r'(\w+\.\w+)\(([^)]*)\)')
    for match in action_pattern.finditer(response_text):
        tool_name = match.group(1)
        args_text = match.group(2)
        arguments = _parse_action_args(args_text)
        # Avoid duplicating if already found via JSON
        if not any(c.tool_name == tool_name and c.arguments == arguments for c in calls):
            calls.append(McpChatToolCall(tool_name=tool_name, arguments=arguments))

    return calls


def _parse_action_args(args_text: str) -> dict[str, Any]:
    """Parse key="value" or key=value pairs from action arguments."""
    args: dict[str, Any] = {}
    for pair in re.finditer(r'(\w+)\s*=\s*(?:"([^"]*)"|(\S+))', args_text):
        key = pair.group(1)
        value = pair.group(2) if pair.group(2) is not None else pair.group(3)
        # Try to convert numeric/boolean values
        if value.isdigit():
            value = int(value)
        elif value.lower() in ("true", "false"):
            value = value.lower() == "true"
        args[key] = value
    return args


# ---------------------------------------------------------------------------
# MCP Tool Router Service
# ---------------------------------------------------------------------------

class McpToolRouterService:
    """Routes LLM tool calls to MCP client and manages the tool-calling loop."""

    def __init__(self) -> None:
        # Store pending confirmations by a confirmation_id
        # Key: confirmation_id, Value: list of pending tool calls
        self._pending_confirmations: dict[str, list[dict[str, Any]]] = {}

    def store_pending_confirmations(self, confirmations: list[dict[str, Any]]) -> str:
        """Store pending confirmations and return a confirmation_id for later reference."""
        from uuid import uuid4
        confirmation_id = f"confirm_{uuid4().hex[:8]}"
        self._pending_confirmations[confirmation_id] = confirmations
        return confirmation_id

    def get_pending_confirmations(self, confirmation_id: str) -> list[dict[str, Any]] | None:
        """Get pending confirmations by ID."""
        return self._pending_confirmations.get(confirmation_id)

    def clear_pending_confirmations(self, confirmation_id: str) -> None:
        """Clear pending confirmations after execution."""
        self._pending_confirmations.pop(confirmation_id, None)

    def _is_cancel_message(self, message: str) -> str | None:
        """Return the latest pending confirmation_id if the user message is a cancel."""
        lower = message.lower().strip()
        cancel_patterns = ["cancel", "no", "nope", "stop", "abort", "don't", "do not", "never mind", "nevermind"]
        if any(lower == p or lower.startswith(p) for p in cancel_patterns):
            if self._pending_confirmations:
                return list(self._pending_confirmations.keys())[-1]
        return None

    def _is_confirmation_message(self, message: str) -> str | None:
        """Check if a user message is a confirmation of pending operations.
        Returns the confirmation_id if found, None otherwise.
        """
        lower = message.lower().strip()
        # Check for explicit confirmation patterns
        confirm_patterns = [
            "yes", "proceed", "confirm", "go ahead", "do it", "execute",
            "approved", "okay", "ok", "sure", "please proceed", "confirmed",
            "yes, proceed", "yes please", "yes do it", "yes confirm",
            "yes, move", "yes, create", "yes, go ahead",
        ]
        if any(lower == p or lower.startswith(p) for p in confirm_patterns):
            # Find the most recent pending confirmation
            if self._pending_confirmations:
                # Return the latest confirmation_id
                return list(self._pending_confirmations.keys())[-1]
        return None

    def execute_pending_confirmations(self, confirmation_id: str) -> dict[str, Any]:
        """Execute all pending operations for a confirmation_id."""
        confirmations = self._pending_confirmations.get(confirmation_id)
        if not confirmations:
            return {"success": False, "error": "No pending confirmations found."}

        results = []
        all_success = True
        for conf in confirmations:
            tool_name = conf.get("tool_name", "")
            arguments = conf.get("arguments", {})
            result = mcp_client.call_tool(tool_name, arguments, confirmed=True)
            results.append({
                "tool_name": tool_name,
                "success": result.success,
                "data": result.data,
                "error": result.error,
            })
            if not result.success:
                all_success = False

        # Clear after execution
        self.clear_pending_confirmations(confirmation_id)

        return {
            "success": all_success,
            "confirmation_id": confirmation_id,
            "results": results,
            "total_operations": len(results),
            "successful_operations": sum(1 for r in results if r["success"]),
        }

    def has_mcp_tools_available(self) -> bool:
        """Check if any MCP tools are available (at least one server enabled)."""
        return len(mcp_client.list_available_tools()) > 0

    def get_tool_schemas_for_llm(self) -> list[dict[str, Any]]:
        """Get tool schemas for the LLM in OpenAI function-calling format."""
        return mcp_client.get_tool_definitions_for_llm()

    def get_mcp_system_prompt(self) -> str:
        """Get the MCP-specific system prompt addition when tools are available."""
        if not self.has_mcp_tools_available():
            return ""
        available = mcp_client.list_available_tools()
        tool_list = "\n".join(
            f"- `{t.name}`: {t.description}" + (" (requires confirmation)" if t.side_effect else "")
            for t in available
        )
        prompt = MCP_SYSTEM_PROMPT_FRAGMENT + f"\nAvailable MCP tools:\n{tool_list}\n"
        # Include configured root_path if available (use resolved path from server instance)
        resolved_root = self._get_configured_root_path()
        if resolved_root:
            prompt += f"\nConfigured root path: {resolved_root}\nWhen the user does not specify a path, use this root_path.\n"
        return prompt

    def _extract_path_from_message(self, message: str) -> str | None:
        """Extract a file system path from a user message."""
        # Windows path: C:\folder or D:/folder
        win_match = re.search(r'([A-Za-z]:[\\\/][^\s,;]+)', message)
        if win_match:
            return win_match.group(1).rstrip(".,;:!?)")
        # Unix path: /home/user, /tmp, etc.
        unix_match = re.search(r'(\/[^\s,;]+)', message)
        if unix_match:
            return unix_match.group(1).rstrip(".,;:!?)")
        return None

    def _get_configured_root_path(self) -> str | None:
        """Get the resolved root_path from the filesystem MCP server instance.

        Uses the server's root_path property (which is validated and resolved
        to an absolute path by apply_config) instead of the raw config dict
        (which may have an incomplete/invalid path like "Demo" without a drive letter).
        """
        try:
            for server in mcp_client.list_servers():
                server_instance = mcp_client._servers.get(server.server_id)
                if server_instance and hasattr(server_instance, "root_path"):
                    # The server instance's root_path is validated and resolved by apply_config.
                    # If it's None, the configured path was invalid — don't fall back to raw config.
                    return getattr(server_instance, "root_path", None)
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Gmail intent safety-net (primary path when a model won't emit tool calls)
    # ------------------------------------------------------------------

    def _is_gmail_intent(self, message: str) -> bool:
        lower = message.lower()
        has_email_word = any(w in lower for w in ["email", "emails", "mail", "inbox", "gmail"]) or bool(self._extract_email(message))
        if not has_email_word:
            return False
        return any(a in lower for a in ["draft", "send", "sent", "compose", "write", "create", "check", "show", "list", "read", "recent", "summarize", "summary", "latest"])

    @staticmethod
    def _extract_email(message: str) -> str | None:
        match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", message)
        return match.group(0) if match else None

    @staticmethod
    def _extract_attachment_query(message: str) -> str:
        lower = message.lower()
        # "resume of <name>" / "<name>'s resume" → include the name so the right
        # person's resume is chosen instead of matching every resume file.
        named = re.search(r"resume of ([a-z'\-]+(?:\s+[a-z'\-]+){0,2})", lower) or re.search(
            r"([a-z'\-]+(?:\s+[a-z'\-]+){0,2})'s resume", lower
        )
        if named:
            stop = {
                "and", "to", "for", "the", "a", "an", "my", "please", "send", "sent",
                "mail", "email", "create", "draft", "compose", "with", "attach", "attaching",
            }
            name = " ".join(w for w in named.group(1).split() if w not in stop)[:60].strip()
            return f"{name} resume".strip() if name else "resume"
        if "resume" in lower or "cv" in lower or "curriculum vitae" in lower:
            return "resume"
        match = re.search(r"attach(?:ing|ment|ed)?\s+(?:the\s+|my\s+|a\s+)?([\w.\- ]{3,40})", lower)
        return match.group(1).strip() if match else ""

    def _summarize_recent_emails(self, emails: list[dict[str, Any]], model_id: str | None) -> str:
        if not emails:
            return "Your recent Gmail inbox looks empty, or I couldn't read any messages."
        listing = "\n".join(
            f"- From {e.get('from_address', '')}: {e.get('subject', '(no subject)')} — {str(e.get('snippet', ''))[:160]}"
            for e in emails[:8]
        )
        try:
            result = model_router_service.generate(
                messages=[
                    {"role": "system", "content": "Summarize the user's recent emails briefly and helpfully. Use only the provided items; do not invent content."},
                    {"role": "user", "content": f"Recent emails:\n{listing}\n\nGive a short, friendly summary."},
                ],
                requested_model_id=model_id,
                options={"temperature": 0.2},
            )
            if result.provider != "fake" and result.reply.strip():
                return result.reply
        except Exception:
            pass
        return "Here are your recent emails:\n" + listing

    def _build_folder_summary_body(self, model_id: str | None) -> str | None:
        """Summarize the connected folder's indexed documents for an email body.
        Brief overview for multiple files; a detailed summary for a single file."""
        docs = file_index_service.list_indexed_file_texts(limit=12, max_chars_each=3000)
        if not docs:
            return None
        if len(docs) == 1:
            instruction = "Write a clear, well-structured summary of the following document."
        else:
            instruction = "Write a brief overview (2-4 short paragraphs) of what these documents are about, and mention the key files by name."
        joined = "\n\n".join(f"### {doc['file_name']}\n{doc['content']}" for doc in docs)[:12000]
        try:
            result = model_router_service.generate(
                messages=[
                    {"role": "system", "content": "You summarize the user's local documents accurately. Use only the provided text. Output only the summary prose (no preamble, no 'Summary:' heading)."},
                    {"role": "user", "content": f"{instruction}\n\nDocuments:\n{joined}"},
                ],
                requested_model_id=model_id,
                options={"temperature": 0.2},
            )
            if result.provider != "fake" and result.reply.strip():
                return result.reply.strip()
        except Exception:
            pass
        return None

    def _handle_gmail_intent(self, user_message: str, model_id: str | None) -> dict[str, Any]:
        display = {"model_used": "gmail", "provider": "gmail", "model_display_name": "Gmail"}
        none: list[dict[str, Any]] = []
        status = gmail_service.status()
        if not status.connected:
            return {"response": "Gmail is not connected. Connect Gmail in Connectors first.", **display, "tool_calls_made": 0, "pending_confirmations": none, "requires_confirmation": False}

        lower = user_message.lower()
        wants_write = any(k in lower for k in ["draft", "send", "sent", "compose", "write", "reply"]) or bool(re.search(r"\b(mail|email)\s+it\b", lower))

        # Read-only: recent emails / summarize inbox
        if not wants_write and any(k in lower for k in ["recent", "check", "latest", "inbox", "summarize", "summary", "show", "list", "read"]):
            result = mcp_client.call_tool("gmail.recent_emails", {"limit": 5}, confirmed=False)
            if not result.success:
                return {"response": result.error or "Could not read recent emails.", **display, "tool_calls_made": 1, "pending_confirmations": none, "requires_confirmation": False}
            emails = (result.data or {}).get("emails", [])
            return {"response": self._summarize_recent_emails(emails, model_id), **display, "tool_calls_made": 1, "pending_confirmations": none, "requires_confirmation": False}

        # Draft / send: compose, resolve attachments, present preview + pending confirmation.
        # A "draft"/"compose" request is never a send, even if the text says "to sent to X".
        wants_draft = "draft" in lower or "compose" in lower
        intent_send = (not wants_draft) and (
            bool(re.search(r"\bsen[dt]\b", lower)) or bool(re.search(r"\b(mail|email)\s+it\b", lower))
        )
        planned = gmail_draft_planner.prepare(
            GmailDraftPrepareRequest(instruction=user_message, connected_email=status.email_address, model_id=model_id)
        )
        display = {
            "model_used": planned.model or "gmail",
            "provider": planned.provider or "gmail",
            "model_display_name": planned.model_display_name or "Gmail",
        }
        recipient = self._extract_email(user_message) or (planned.to or "").strip()
        if not recipient:
            return {"response": "Who should I send this to? Please give me a recipient email address.", **display, "tool_calls_made": 0, "pending_confirmations": none, "requires_confirmation": False}

        resolved = gmail_mcp_server.resolve_attachment_candidates(self._extract_attachment_query(user_message), None)
        if resolved["candidates"]:
            options = "\n".join(f"- {c['file_name']}" for c in resolved["candidates"])
            return {"response": f"I found multiple matching files. Which one should I attach?\n{options}", **display, "tool_calls_made": 0, "pending_confirmations": none, "requires_confirmation": False}

        # If the user asked to summarize the folder/documents, build the body from the
        # connected folder's already-indexed content (brief for many, detailed for one).
        subject = planned.subject
        body = planned.body
        if any(k in lower for k in ["summar", "overview", "about", "contents", "what's in", "whats in", "document", "folder"]):
            summary_body = self._build_folder_summary_body(model_id)
            if summary_body:
                body = f"Hi,\n\n{summary_body}\n\nBest regards,"

        tool_name = "gmail.send_email" if intent_send else "gmail.create_draft"
        args = {"to": recipient, "subject": subject, "body": body, "attachment_paths": resolved["attachment_paths"]}
        preview_result = mcp_client.call_tool(tool_name, args, confirmed=False)
        kind = "gmail_send" if intent_send else "gmail_draft"
        pending = [{"tool_name": tool_name, "arguments": args, "preview": preview_result.preview, "requires_confirmation": True, "kind": kind}]

        lines = ["Here's the draft I prepared:", "", f"To: {recipient}", f"Subject: {subject}"]
        if resolved["attachments"]:
            lines.append(f"Attachment: {', '.join(resolved['attachments'])}")
        elif resolved["note"]:
            lines.append(f"({resolved['note']})")
        lines += ["", body]
        return {"response": "\n".join(lines), **display, "tool_calls_made": 0, "pending_confirmations": pending, "requires_confirmation": True, "confirmation_kind": kind}

    # ------------------------------------------------------------------
    # File System MCP document Q&A safety-net
    # ------------------------------------------------------------------

    def _is_filesystem_document_intent(self, message: str) -> bool:
        lower = message.lower()
        if self._is_gmail_intent(message):
            return False
        action_hit = any(
            word in lower
            for word in [
                "summarize",
                "summary",
                "overview",
                "read",
                "explain",
                "what does",
                "what is in",
                "answer from",
                "question about",
                "tell me about",
            ]
        )
        doc_hit = any(
            word in lower
            for word in [
                "resume",
                "cv",
                "document",
                "docx",
                "pdf",
                "ppt",
                "pptx",
                "presentation",
                ".txt",
                ".md",
                ".json",
                ".csv",
                ".py",
                ".js",
                ".ts",
                ".html",
                ".css",
            ]
        )
        named_file_hit = bool(re.search(r"[\w .\-]+\.(pdf|docx|pptx|txt|md|log|json|csv|xml|ya?ml|py|js|ts|tsx|jsx|html|css|java|sql)\b", lower))
        return action_hit and (doc_hit or named_file_hit)

    def _extract_document_query(self, message: str) -> str:
        lower = message.lower()
        file_match = re.search(r"([\w .\-]+\.(?:pdf|docx|pptx|txt|md|log|json|csv|xml|ya?ml|py|js|ts|tsx|jsx|html|css|java|sql))\b", message, re.IGNORECASE)
        if file_match:
            return file_match.group(1).strip()
        if "resume" in lower or "cv" in lower:
            return "resume cv"
        if "pptx" in lower or "ppt" in lower or "presentation" in lower:
            return "pptx presentation slides"
        quoted = re.search(r"['\"]([^'\"]{2,80})['\"]", message)
        if quoted:
            return quoted.group(1).strip()
        cleaned = re.sub(
            r"\b(summarize|summary|overview|read|explain|what|does|this|my|the|file|document|answer|from|about|give|me|an|a|of|please)\b",
            " ",
            lower,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or message

    def _handle_filesystem_document_intent(self, user_message: str, model_id: str | None) -> dict[str, Any]:
        none: list[dict[str, Any]] = []
        root_path = self._get_configured_root_path()
        display = {"model_used": "filesystem", "provider": "mcp", "model_display_name": "File System MCP"}
        if not root_path:
            return {
                "response": "File System MCP does not have a root folder configured yet. Set the MCP root folder first, then I can read and answer from your documents.",
                **display,
                "tool_calls_made": 0,
                "pending_confirmations": none,
                "requires_confirmation": False,
            }

        query = self._extract_document_query(user_message)
        tool_calls_made = 0
        search_result = mcp_client.call_tool("fs.search_files", {"query": query, "limit": 5}, confirmed=False)
        tool_calls_made += 1
        matches = ((search_result.data or {}).get("matches", []) if search_result.success and isinstance(search_result.data, dict) else [])

        if not matches:
            index_result = mcp_client.call_tool("fs.index_folder", {"root_path": root_path}, confirmed=False)
            tool_calls_made += 1
            if not index_result.success:
                return {
                    "response": index_result.error or "I could not index the configured File System MCP folder.",
                    **display,
                    "tool_calls_made": tool_calls_made,
                    "pending_confirmations": none,
                    "requires_confirmation": False,
                }
            search_result = mcp_client.call_tool("fs.search_files", {"query": query, "limit": 5}, confirmed=False)
            tool_calls_made += 1
            matches = ((search_result.data or {}).get("matches", []) if search_result.success and isinstance(search_result.data, dict) else [])

        if not matches:
            return {
                "response": f"I indexed the configured folder, but I could not find a readable document matching '{query}'.",
                **display,
                "tool_calls_made": tool_calls_made,
                "pending_confirmations": none,
                "requires_confirmation": False,
            }

        selected = matches[0]
        read_result = mcp_client.call_tool("fs.read_file", {"event_id": selected.get("event_id")}, confirmed=False)
        tool_calls_made += 1
        if not read_result.success or not isinstance(read_result.data, dict):
            return {
                "response": read_result.error or "I found a matching file, but could not read its extracted text.",
                **display,
                "tool_calls_made": tool_calls_made,
                "pending_confirmations": none,
                "requires_confirmation": False,
            }

        data = read_result.data
        file_name = str(data.get("file_name") or selected.get("file_name") or "selected file")
        relative_path = str(data.get("relative_path") or selected.get("relative_path") or file_name)
        content = str(data.get("content") or "")[:14000]
        visual_status = str(data.get("visual_extraction_status") or "not_required")
        close_matches = [m for m in matches[1:3] if float(m.get("score") or 0) >= max(0.35, float(selected.get("score") or 0) - 0.2)]
        selection_note = f"I selected `{relative_path}`"
        if close_matches:
            alternatives = ", ".join(str(match.get("relative_path") or match.get("file_name")) for match in close_matches)
            selection_note += f" as the strongest match. Other close matches: {alternatives}."
        else:
            selection_note += "."

        if not content.strip():
            limitation = " It looks image-heavy, so visual extraction is needed but not available for this text-only read." if visual_status == "needed" else ""
            return {
                "response": f"{selection_note}\n\nI found the file, but no readable text was extracted.{limitation}",
                **display,
                "tool_calls_made": tool_calls_made,
                "pending_confirmations": none,
                "requires_confirmation": False,
            }

        try:
            answer = model_router_service.generate(
                messages=[
                    {
                        "role": "system",
                        "content": "Answer the user's question using only the extracted local file text. Be concise and mention uncertainty or visual extraction limits when relevant.",
                    },
                    {
                        "role": "user",
                        "content": (
                            f"User request: {user_message}\n\n"
                            f"Selected file: {relative_path}\n"
                            f"Visual extraction status: {visual_status}\n\n"
                            f"Extracted text:\n{content}"
                        ),
                    },
                ],
                requested_model_id=model_id,
                options={"temperature": 0.2},
            )
            response = f"{selection_note}\n\n{answer.reply.strip()}"
            if visual_status == "needed":
                response += "\n\nNote: this file may contain visual content that was not read by text extraction."
            return {
                "response": response,
                "model_used": answer.model_used,
                "provider": answer.provider,
                "model_display_name": answer.model_display_name,
                "tool_calls_made": tool_calls_made,
                "pending_confirmations": none,
                "requires_confirmation": False,
            }
        except Exception:
            excerpt = content[:1600].rsplit(" ", 1)[0]
            return {
                "response": f"{selection_note}\n\nHere is the readable text I found in `{file_name}`:\n\n{excerpt}",
                **display,
                "tool_calls_made": tool_calls_made,
                "pending_confirmations": none,
                "requires_confirmation": False,
            }

    def _deterministic_tool_fallback(self, user_message: str) -> list[McpChatToolCall]:
        """When the LLM fails to generate tool calls, deterministically decide
        which MCP tool to call based on the user message content."""
        lower = user_message.lower()
        root_path = self._extract_path_from_message(user_message) or self._get_configured_root_path()
        if not root_path:
            return []

        # Detect intent and map to a tool call
        scan_keywords = ["list", "show", "scan", "what", "files", "folder", "directory", "inside", "contents", "content"]
        organize_keywords = ["organize", "sort", "clean", "move", "group", "arrange"]
        summary_keywords = ["summary", "summarize", "overview", "describe"]

        hit_scan = sum(1 for kw in scan_keywords if kw in lower)
        hit_organize = sum(1 for kw in organize_keywords if kw in lower)
        hit_summary = sum(1 for kw in summary_keywords if kw in lower)

        if hit_organize >= 1:
            return [McpChatToolCall(tool_name="fs.organize_plan", arguments={"root_path": root_path, "instruction": user_message})]
        if hit_summary >= 1 and hit_scan == 0:
            return [McpChatToolCall(tool_name="fs.folder_summary", arguments={"root_path": root_path})]
        if hit_scan >= 1:
            # A genuine scan/listing intent — safest read-only first step
            return [McpChatToolCall(tool_name="fs.scan_folder", arguments={"root_path": root_path})]

        return []

    def _extract_plan_operations_as_confirmations(self, results: list[McpChatToolResult]) -> list[dict[str, Any]]:
        """When fs.organize_plan returns a plan, extract the individual operations
        (create_folder, move_file) and convert them into pending confirmations
        that can be executed when the user confirms."""
        confirmations: list[dict[str, Any]] = []
        for r in results:
            if not r.success or r.tool_name != "fs.organize_plan":
                continue
            plan_data = r.result
            if not isinstance(plan_data, dict):
                continue
            operations = plan_data.get("operations", [])
            root_path = plan_data.get("root_path", "")
            for op in operations:
                op_type = op.get("type", "")
                if op_type == "create_folder":
                    folder_path = op.get("path", "")
                    confirmations.append({
                        "tool_name": "fs.create_folder",
                        "arguments": {
                            "root_path": root_path,
                            "folder_path": folder_path,
                        },
                        "preview": {
                            "type": "create_folder",
                            "path": op.get("relative_to", folder_path),
                            "reason": op.get("reason", ""),
                        },
                        "requires_confirmation": True,
                    })
                elif op_type == "move_file":
                    confirmations.append({
                        "tool_name": "fs.move_file",
                        "arguments": {
                            "root_path": root_path,
                            "from_path": op.get("from_path", ""),
                            "to_path": op.get("to_path", ""),
                        },
                        "preview": {
                            "type": "move_file",
                            "from": op.get("relative_from", op.get("from_path", "")),
                            "to": op.get("relative_to", op.get("to_path", "")),
                            "reason": op.get("reason", ""),
                        },
                        "requires_confirmation": True,
                    })
        return confirmations

    def execute_tool_calls(
        self,
        tool_calls: list[McpChatToolCall],
        confirmed: bool = False,
    ) -> list[McpChatToolResult]:
        """Execute a list of tool calls through the MCP client.

        Read-only tools are executed immediately.
        Side-effect tools require confirmed=True.
        """
        results: list[McpChatToolResult] = []
        for call in tool_calls:
            result = mcp_client.call_tool(call.tool_name, call.arguments, confirmed=confirmed)
            results.append(McpChatToolResult(
                tool_name=call.tool_name,
                success=result.success,
                result=result.data,
                error=result.error,
                requires_confirmation=result.requires_confirmation,
            ))
        return results

    def execute_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        confirmed: bool = False,
    ) -> McpChatToolResult:
        """Execute a single tool call."""
        result = mcp_client.call_tool(tool_name, arguments, confirmed=confirmed)
        return McpChatToolResult(
            tool_name=tool_name,
            success=result.success,
            result=result.data,
            error=result.error,
            requires_confirmation=result.requires_confirmation,
        )

    def format_tool_results_for_llm(self, results: list[McpChatToolResult]) -> str:
        """Format tool results as a readable message to feed back to the LLM."""
        parts: list[str] = []
        for r in results:
            if r.success:
                parts.append(f"Tool `{r.tool_name}` result:\n{json.dumps(r.result, indent=2, default=str)}")
            else:
                msg = f"Tool `{r.tool_name}` error: {r.error}"
                if r.requires_confirmation:
                    msg += "\nThis operation requires user confirmation before it can be executed."
                parts.append(msg)
        return "\n\n".join(parts)

    def detect_tool_calls_in_response(self, response_text: str) -> list[McpChatToolCall]:
        """Check if an LLM response contains tool calls that need execution."""
        calls = parse_tool_calls_from_llm_response(response_text)
        # Filter to only known MCP tools
        known_tools = {t.name for t in mcp_client.list_available_tools()}
        return [c for c in calls if c.tool_name in known_tools]

    def process_chat_with_mcp(
        self,
        user_message: str,
        context_text: str,
        model_id: str | None = None,
        max_rounds: int = 3,
    ) -> dict[str, Any]:
        """Process a chat message with MCP tool-calling capability.

        This implements a tool-calling loop:
        1. Send user message + context + tool schemas to LLM
        2. If LLM response contains tool calls, execute read-only ones
        3. Feed results back to LLM
        4. Repeat until no more tool calls or max rounds reached

        Returns a dict with the final response and any pending confirmations.
        """
        mcp_prompt = self.get_mcp_system_prompt()
        tool_schemas = self.get_tool_schemas_for_llm()

        messages: list[dict[str, str]] = [
            {"role": "system", "content": mcp_prompt + "\n\nContext:\n" + context_text},
            {"role": "user", "content": user_message},
        ]

        pending_confirmations: list[dict[str, Any]] = []
        tool_results_log: list[dict[str, Any]] = []

        # Gmail intents always use the reliable deterministic handler (compose →
        # preview → confirm), BEFORE asking the model. Local models otherwise emit
        # unreliable/garbled tool calls for email and the draft/send never runs.
        if self._is_gmail_intent(user_message):
            return self._handle_gmail_intent(user_message, model_id)

        for round_num in range(max_rounds):
            result = model_router_service.generate(
                messages=messages,
                requested_model_id=model_id,
                options={"temperature": 0.1},
            )

            response_text = result.reply

            # Check for tool calls in the response
            tool_calls = self.detect_tool_calls_in_response(response_text)

            if not tool_calls:
                # LLM didn't generate tool calls — try deterministic fallback on first round
                if round_num == 0 and not tool_results_log:
                    # (Gmail intents are already short-circuited before the loop.)
                    if self._is_filesystem_document_intent(user_message):
                        return self._handle_filesystem_document_intent(user_message, model_id)
                    fallback_calls = self._deterministic_tool_fallback(user_message)
                    if fallback_calls:
                        # Execute the fallback tool call directly
                        fb_results = self.execute_tool_calls(fallback_calls, confirmed=False)
                        fb_results_text = self.format_tool_results_for_llm(fb_results)
                        tool_results_log.extend([{"tool": r.tool_name, "success": r.success, "fallback": True} for r in fb_results])

                        # Auto-extract operations from an organize_plan result as pending
                        # confirmations (mirrors the main read-only branch). Without this,
                        # a plan produced via the fallback path has nothing for "yes" to execute.
                        plan_confirmations = self._extract_plan_operations_as_confirmations(fb_results)
                        if plan_confirmations:
                            pending_confirmations.extend(plan_confirmations)
                            tool_results_log.append({"tool": "fs.organize_plan", "success": True, "extracted_operations": len(plan_confirmations)})

                        # Check for side-effect fallback calls
                        fb_side_effects = []
                        fb_readonly = []
                        for call in fallback_calls:
                            tool_def = None
                            for t in mcp_client.list_available_tools():
                                if t.name == call.tool_name:
                                    tool_def = t
                                    break
                            if tool_def and tool_def.side_effect:
                                fb_side_effects.append(call)
                            else:
                                fb_readonly.append(call)

                        if fb_side_effects:
                            for call in fb_side_effects:
                                preview_result = mcp_client.call_tool(call.tool_name, call.arguments, confirmed=False)
                                pending_confirmations.append({
                                    "tool_name": call.tool_name,
                                    "arguments": call.arguments,
                                    "preview": preview_result.preview,
                                    "requires_confirmation": True,
                                })

                        # Feed fallback results to LLM for a natural response. If a plan was
                        # extracted, steer the model to summarize and ask for confirmation
                        # (and not to call the side-effect tools itself).
                        followup = (
                            "I ran the organize plan automatically. Here are the results:\n"
                            f"{fb_results_text}\n\nPlease summarize the planned operations for the user "
                            "and tell them they can confirm by saying 'yes' or 'proceed'. "
                            "Do NOT try to call fs.create_folder or fs.move_file yourself."
                            if plan_confirmations
                            else f"I executed the tool automatically. Here are the results:\n{fb_results_text}\n\nPlease summarize these results for the user in a clear, helpful way."
                        )
                        messages.append({"role": "assistant", "content": response_text})
                        messages.append({"role": "user", "content": followup})
                        summary_result = model_router_service.generate(
                            messages=messages,
                            requested_model_id=model_id,
                            options={"temperature": 0.1},
                        )
                        return {
                            "response": summary_result.reply,
                            "model_used": summary_result.model_used,
                            "provider": summary_result.provider,
                            "model_display_name": summary_result.model_display_name,
                            "tool_calls_made": len(tool_results_log),
                            "pending_confirmations": pending_confirmations,
                            "requires_confirmation": len(pending_confirmations) > 0,
                        }

                # No tool calls and no fallback — return the final response
                return {
                    "response": response_text,
                    "model_used": result.model_used,
                    "provider": result.provider,
                    "model_display_name": result.model_display_name,
                    "tool_calls_made": len(tool_results_log),
                    "pending_confirmations": pending_confirmations,
                    "requires_confirmation": len(pending_confirmations) > 0,
                }

            # Execute read-only tool calls and collect side-effect ones
            readonly_calls = []
            side_effect_calls = []
            for call in tool_calls:
                tool_def = None
                for t in mcp_client.list_available_tools():
                    if t.name == call.tool_name:
                        tool_def = t
                        break
                if tool_def and tool_def.side_effect:
                    side_effect_calls.append(call)
                else:
                    readonly_calls.append(call)

            # Execute read-only calls immediately
            if readonly_calls:
                results = self.execute_tool_calls(readonly_calls, confirmed=False)
                results_text = self.format_tool_results_for_llm(results)
                tool_results_log.extend([{"tool": r.tool_name, "success": r.success} for r in results])

                # Auto-extract operations from organize_plan results as pending confirmations
                plan_confirmations = self._extract_plan_operations_as_confirmations(results)
                if plan_confirmations:
                    pending_confirmations.extend(plan_confirmations)
                    tool_results_log.append({"tool": "fs.organize_plan", "success": True, "extracted_operations": len(plan_confirmations)})

                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "user", "content": f"Tool results:\n{results_text}"})

                # If we extracted plan operations, tell the LLM to summarize and ask for confirmation
                if plan_confirmations:
                    messages.append({
                        "role": "user",
                        "content": "The organize plan has been generated. Please summarize the planned operations for the user "
                        "and tell them they can confirm by saying 'yes' or 'proceed'. Do NOT try to call fs.create_folder or fs.move_file yourself.",
                    })
                    confirm_result = model_router_service.generate(
                        messages=messages,
                        requested_model_id=model_id,
                        options={"temperature": 0.1},
                    )
                    return {
                        "response": confirm_result.reply,
                        "model_used": confirm_result.model_used,
                        "provider": confirm_result.provider,
                        "model_display_name": confirm_result.model_display_name,
                        "tool_calls_made": len(tool_results_log),
                        "pending_confirmations": pending_confirmations,
                        "requires_confirmation": True,
                    }

            # Collect side-effect calls as pending confirmations
            for call in side_effect_calls:
                preview_result = mcp_client.call_tool(call.tool_name, call.arguments, confirmed=False)
                pending_confirmations.append({
                    "tool_name": call.tool_name,
                    "arguments": call.arguments,
                    "preview": preview_result.preview,
                    "requires_confirmation": True,
                })
                tool_results_log.append({"tool": call.tool_name, "success": False, "pending_confirmation": True})

            # If only side-effect calls were found, tell LLM and break
            if side_effect_calls and not readonly_calls:
                messages.append({"role": "assistant", "content": response_text})
                messages.append({
                    "role": "user",
                    "content": "The requested action requires user confirmation. "
                    "Please review the planned action(s) below and ask the user to reply yes or proceed to run them.",
                })
                # One more LLM call to generate the confirmation message
                confirm_result = model_router_service.generate(
                    messages=messages,
                    requested_model_id=model_id,
                    options={"temperature": 0.1},
                )
                return {
                    "response": confirm_result.reply,
                    "model_used": confirm_result.model_used,
                    "provider": confirm_result.provider,
                    "model_display_name": confirm_result.model_display_name,
                    "tool_calls_made": len(tool_results_log),
                    "pending_confirmations": pending_confirmations,
                    "requires_confirmation": True,
                }

        # Max rounds reached
        return {
            "response": response_text,
            "model_used": result.model_used,
            "provider": result.provider,
            "model_display_name": result.model_display_name,
            "tool_calls_made": len(tool_results_log),
            "pending_confirmations": pending_confirmations,
            "requires_confirmation": len(pending_confirmations) > 0,
        }


mcp_tool_router_service = McpToolRouterService()
