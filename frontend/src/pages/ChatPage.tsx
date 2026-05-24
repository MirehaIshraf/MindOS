import { History, MessageSquare, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ChatInput } from "../components/chat/ChatInput";
import { ChatMessage } from "../components/chat/ChatMessage";
import { Badge } from "../components/shared/Badge";
import { Button } from "../components/shared/Button";
import { deleteChatSession, getChatMessages, getChatSessions, sendChatMessage } from "../services/api";
import type { ChatMessage as ChatMessageRecord, ChatSession, StoredChatMessage } from "../types";

const examplePrompts = [
  "What did I work on this week?",
  "Why did the deployment fail?",
  "Find the authentication bug I fixed before",
  "Draft a Jira ticket from recent errors",
];

export function ChatPage() {
  const navigate = useNavigate();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessageRecord[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [isReplying, setIsReplying] = useState(false);
  const [loadingSessionId, setLoadingSessionId] = useState<string | null>(null);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [useContext, setUseContext] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void refreshSessions();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isReplying]);

  async function refreshSessions() {
    setSessionError(null);
    try {
      const response = await getChatSessions();
      setSessions(response.sessions);
    } catch {
      setSessionError("Could not load recent chats.");
    }
  }

  async function handleSend() {
    const content = input.trim();
    if (!content || isReplying) {
      return;
    }

    const userMessage = createMessage("user", content);
    const history = messages.map((message) => ({
      role: message.role,
      content: message.content,
      timestamp: message.timestamp,
    }));

    setMessages((current) => [...current, userMessage]);
    setInput("");
    setIsReplying(true);

    try {
      const response = await sendChatMessage({
        message: content,
        history,
        use_context: useContext,
        session_id: currentSessionId,
      });
      setCurrentSessionId(response.session_id);
      setMessages((current) => [
        ...current,
        createMessage("assistant", response.reply, {
          sourcesUsed: response.sources_used,
          model: response.model,
          searchMode: response.search_mode,
          taskHint: response.task_hint,
          taskInstruction: content,
        }),
      ]);
      await refreshSessions();
    } catch {
      setMessages((current) => [
        ...current,
        createMessage("assistant", "MindOS backend is offline or chat failed. Please check Developer Mode."),
      ]);
    } finally {
      setIsReplying(false);
    }
  }

  function handleNewChat() {
    setMessages([]);
    setInput("");
    setCurrentSessionId(null);
    setIsReplying(false);
  }

  async function handleLoadSession(sessionId: string) {
    setLoadingSessionId(sessionId);
    setSessionError(null);
    try {
      const response = await getChatMessages(sessionId);
      setCurrentSessionId(sessionId);
      setMessages(mapStoredMessages(response.messages));
      setSessionsOpen(false);
    } catch {
      setSessionError("Could not load that chat.");
    } finally {
      setLoadingSessionId(null);
    }
  }

  async function handleDeleteSession(sessionId: string) {
    setLoadingSessionId(sessionId);
    setSessionError(null);
    try {
      await deleteChatSession(sessionId);
      if (currentSessionId === sessionId) {
        handleNewChat();
      }
      await refreshSessions();
    } catch {
      setSessionError("Could not delete that chat.");
    } finally {
      setLoadingSessionId(null);
    }
  }

  return (
    <div className="mx-auto flex min-h-[calc(100vh-8rem)] max-w-[850px] flex-col">
      <div className="mb-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm text-app-muted">
            <Badge variant="info">{currentSessionId ? "Saved chat" : "New chat"}</Badge>
            {sessionError ? <span className="text-red-300">{sessionError}</span> : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="ghost" onClick={() => void refreshSessions()}>
              <RefreshCw size={16} />
              Refresh
            </Button>
            <Button type="button" variant="secondary" onClick={() => setSessionsOpen((open) => !open)}>
              <History size={16} />
              Recent Chats
            </Button>
            <Button type="button" variant="secondary" onClick={handleNewChat}>
              <Plus size={16} />
              New Chat
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={handleNewChat}
              disabled={messages.length === 0 && input.length === 0}
            >
              <Trash2 size={16} />
              Clear Chat
            </Button>
          </div>
        </div>

        {sessionsOpen ? (
          <div className="rounded-md border border-app-border bg-app-panel p-3">
            {sessions.length === 0 ? (
              <p className="text-sm text-app-muted">No saved chats yet.</p>
            ) : (
              <div className="space-y-2">
                {sessions.map((session) => (
                  <div key={session.id} className="flex items-center gap-3 rounded-md border border-app-border bg-zinc-950 px-3 py-2">
                    <button
                      type="button"
                      className="min-w-0 flex-1 text-left"
                      onClick={() => void handleLoadSession(session.id)}
                      disabled={loadingSessionId === session.id}
                    >
                      <p className="truncate text-sm font-medium text-app-text">{session.title}</p>
                      <p className="mt-1 text-xs text-app-muted">{formatTimestamp(session.updated_at)}</p>
                    </button>
                    {currentSessionId === session.id ? <Badge variant="success">open</Badge> : null}
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => void handleDeleteSession(session.id)}
                      loading={loadingSessionId === session.id}
                    >
                      <Trash2 size={16} />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : null}
      </div>

      <div className="flex-1 space-y-4 pb-6">
        {messages.length === 0 ? (
          <div className="flex min-h-[420px] flex-col items-center justify-center px-8 text-center">
            <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-lg bg-app-primary text-white shadow-sm shadow-violet-950/40">
              <MessageSquare size={28} />
            </div>
            <h1 className="text-3xl font-semibold text-app-text">MindOS</h1>
            <p className="mt-3 text-base text-app-text">Your local AI workspace with memory of your work.</p>
            <p className="mt-4 max-w-2xl text-sm leading-6 text-app-muted">
              Ask about your files, code editor activity, browser research, GitHub, Jira, logs, emails, or ask MindOS
              to prepare a task.
            </p>
            <div className="mt-8 flex max-w-3xl flex-wrap justify-center gap-3">
              {examplePrompts.map((prompt) => (
                <button key={prompt} type="button" onClick={() => setInput(prompt)}>
                  <Badge variant="info">{prompt}</Badge>
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <ChatMessage
              key={message.id}
              message={message}
              onOpenTask={(instruction) => navigate(`/tasks?instruction=${encodeURIComponent(instruction)}`)}
            />
          ))
        )}

        {isReplying ? (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-md border border-app-border bg-app-panel px-4 py-3 text-sm text-app-muted">
              Thinking over local memory...
            </div>
          </div>
        ) : null}

        <div ref={messagesEndRef} />
      </div>

      <div className="sticky bottom-0 bg-app-background pb-4 pt-3">
        <ChatInput
          value={input}
          onChange={setInput}
          onSend={handleSend}
          disabled={isReplying}
          useContext={useContext}
          onUseContextChange={setUseContext}
        />
      </div>
    </div>
  );
}

function mapStoredMessages(storedMessages: StoredChatMessage[]): ChatMessageRecord[] {
  let lastUserInstruction = "";
  return storedMessages.map((message) => {
    if (message.role === "user") {
      lastUserInstruction = message.content;
    }

    return {
      id: message.id,
      role: message.role === "assistant" ? "assistant" : "user",
      content: message.content,
      timestamp: message.created_at,
      sourcesUsed: message.sources_used ?? [],
      model: message.model ?? undefined,
      searchMode: message.search_mode ?? undefined,
      taskHint: message.task_hint ?? undefined,
      taskInstruction: message.role === "assistant" ? lastUserInstruction : undefined,
    };
  });
}

function createMessage(
  role: ChatMessageRecord["role"],
  content: string,
  extra: Partial<Omit<ChatMessageRecord, "id" | "role" | "content" | "timestamp">> = {},
): ChatMessageRecord {
  return {
    id: crypto.randomUUID(),
    role,
    content,
    timestamp: new Date().toISOString(),
    ...extra,
  };
}

function formatTimestamp(value: string) {
  return new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
