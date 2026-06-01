import { History, MessageSquare, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ChatInput } from "../components/chat/ChatInput";
import { ChatMessage } from "../components/chat/ChatMessage";
import { Badge } from "../components/shared/Badge";
import { Button } from "../components/shared/Button";
import { deleteChatSession, getChatMessages, getChatSessions, getChatModelsResponse, selectChatModel, sendChatMessage } from "../services/api";
import type { ChatMessage as ChatMessageRecord, ChatSession, ModelConfig, StoredChatMessage } from "../types";

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
  const [pendingStyle, setPendingStyle] = useState("normal");
  const [statusIndex, setStatusIndex] = useState(0);
  const [loadingSessionId, setLoadingSessionId] = useState<string | null>(null);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [useContext, setUseContext] = useState(true);
  const [chatModels, setChatModels] = useState<ModelConfig[]>([]);
  const [selectedModelId, setSelectedModelId] = useState<string>("");
  const [modelError, setModelError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void refreshSessions();
    void refreshChatModels();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isReplying]);

  useEffect(() => {
    if (!isReplying) {
      setStatusIndex(0);
      return;
    }
    const intervalId = window.setInterval(() => {
      setStatusIndex((current) => current + 1);
    }, 1500);
    return () => window.clearInterval(intervalId);
  }, [isReplying]);

  const loadingMessages = useMemo(() => loadingStatusMessages(pendingStyle), [pendingStyle]);
  const selectedModel = chatModels.find((model) => model.id === selectedModelId) ?? chatModels[0];

  async function refreshSessions() {
    setSessionError(null);
    try {
      const response = await getChatSessions();
      setSessions(response.sessions);
    } catch {
      setSessionError("Could not load recent chats.");
    }
  }

  async function refreshChatModels() {
    setModelError(null);
    try {
      const response = await getChatModelsResponse();
      const models = response.models.length > 0 ? response.models : [fakeModel()];
      setChatModels(models);
      setSelectedModelId((current) =>
        current || (models.some((model) => model.id === response.selected_chat_model) ? response.selected_chat_model : models[0].id),
      );
      setModelError(response.warning ?? null);
    } catch (caughtError) {
      console.error("Could not load chat models.", caughtError);
      const fallback = fakeModel();
      setChatModels([fallback]);
      setSelectedModelId((current) => current || fallback.id);
      setModelError("Model settings unavailable. Using fallback.");
    }
  }

  async function handleModelChange(modelId: string) {
    setSelectedModelId(modelId);
    setModelError(null);
    try {
      await selectChatModel(modelId);
    } catch {
      setModelError("Could not save selected model. This chat will still try it.");
    }
  }

  async function handleSend() {
    const content = input.trim();
    if (!content || isReplying) {
      return;
    }

    const userMessage = createMessage("user", content);
    const style = detectPendingStyle(content);
    const history = messages.map((message) => ({
      role: message.role,
      content: message.content,
      timestamp: message.timestamp,
    }));

    setMessages((current) => [...current, userMessage]);
    setInput("");
    setPendingStyle(style);
    setIsReplying(true);

    try {
      const response = await sendChatMessage({
        message: content,
        history,
        use_context: useContext,
        session_id: currentSessionId,
        model_id: selectedModelId || undefined,
      });
      setCurrentSessionId(response.session_id);
      setMessages((current) => [
        ...current,
        createMessage("assistant", response.reply, {
          sourcesUsed: response.sources_used,
          model: response.model,
          provider: response.provider,
          modelDisplayName: response.model_display_name,
          searchMode: response.search_mode,
          taskHint: response.task_hint,
          taskInstruction: content,
          contextSummary: response.context_summary,
          contextStats: response.context_stats,
          warning: response.warning,
          answerStyle: response.answer_style,
          intent: response.intent,
          isFollowUp: response.is_follow_up,
          resolvedQuery: response.resolved_query,
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
    <div className="mx-auto flex min-h-[calc(100vh-8rem)] w-full max-w-[900px] flex-col">
      <div className="relative mb-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={selectedModelId}
              onChange={(event) => void handleModelChange(event.target.value)}
              className="h-10 min-w-48 rounded-md border border-app-border bg-app-panel px-3 text-sm text-app-text outline-none focus:border-app-primary"
              aria-label="Chat model"
            >
              {chatModels.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.display_name}
                </option>
              ))}
            </select>
            {selectedModel ? <Badge variant={selectedModel.type === "cloud" ? "warning" : "success"}>{selectedModel.type === "cloud" ? "Cloud" : "Local"}</Badge> : null}
            {selectedModel?.model_id.toLowerCase().includes("llama3.2:1b") ? <Badge variant="info">Speed</Badge> : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="secondary" onClick={() => setSessionsOpen((open) => !open)}>
              <History size={16} />
              Recent Chats
            </Button>
            <Button type="button" variant="secondary" onClick={handleNewChat}>
              <Plus size={16} />
              New Chat
            </Button>
          </div>
        </div>
        {modelError ? <p className="text-xs text-amber-200">{modelError}</p> : null}
        {sessionError ? <p className="text-xs text-red-300">{sessionError}</p> : null}

        {sessionsOpen ? (
          <div className="absolute right-0 z-20 w-full max-w-md rounded-md border border-app-border bg-app-panel p-3 shadow-xl shadow-black/30">
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
        {selectedModel?.type === "cloud" ? (
          <p className="text-xs text-amber-200">Cloud model: selected memory context may be sent to provider.</p>
        ) : null}
      </div>

      <div className="flex-1 space-y-4 pb-6">
        {messages.length === 0 ? (
          <div className="flex min-h-[420px] flex-col items-center justify-center px-8 text-center">
            <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-lg bg-app-primary text-white shadow-sm shadow-violet-950/40">
              <MessageSquare size={28} />
            </div>
            <h1 className="text-3xl font-semibold text-app-text">MindOS</h1>
            <p className="mt-3 text-base text-app-text">Ask about your local work memory.</p>
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
              onOpenTask={(instruction) =>
                navigate(
                  `/tasks?instruction=${encodeURIComponent(instruction)}${
                    selectedModelId ? `&model_id=${encodeURIComponent(selectedModelId)}` : ""
                  }`,
                )
              }
            />
          ))
        )}

        {isReplying ? (
          <div className="flex justify-start">
            <div className="px-2 py-1 text-sm text-app-muted">{loadingMessages[statusIndex % loadingMessages.length]}</div>
          </div>
        ) : null}

        <div ref={messagesEndRef} />
      </div>

      <div className="sticky bottom-0 bg-app-background pb-4 pt-3">
        <p className="mb-2 text-xs text-app-muted">{useContext ? "Using local memory" : "Local memory off"}</p>
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

function fakeModel(): ModelConfig {
  return {
    id: "fake-llm",
    provider: "fake",
    display_name: "FakeLLM fallback",
    model_id: "fake-llm",
    type: "local",
    enabled: true,
    configured: true,
    available: true,
    status: "available",
    supports_tools: false,
    supports_vision: false,
    default_context_profile: "fast_chat",
    privacy_level: "local_private",
    description: "Fallback development model",
  };
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
      provider: message.provider ?? undefined,
      modelDisplayName: message.model_display_name ?? undefined,
      searchMode: message.search_mode ?? undefined,
      taskHint: message.task_hint ?? undefined,
      taskInstruction: message.role === "assistant" ? lastUserInstruction : undefined,
      contextSummary: message.context_summary ?? undefined,
      contextStats: message.context_stats ?? undefined,
      warning: message.warning ?? undefined,
      answerStyle: message.answer_style ?? undefined,
      intent: message.intent ?? undefined,
      isFollowUp: Boolean(message.is_follow_up ?? message.metadata?.is_follow_up),
      resolvedQuery: message.resolved_query ?? (typeof message.metadata?.resolved_query === "string" ? message.metadata.resolved_query : undefined),
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

function loadingStatusMessages(style: string) {
  if (style === "task") {
    return ["Understanding task request...", "Checking relevant memory...", "Preparing safe task preview..."];
  }
  if (style === "root_cause") {
    return [
      "Searching local memory...",
      "Checking logs, tasks, files, and related events...",
      "Preparing root-cause analysis...",
    ];
  }
  if (style === "memory_lookup") {
    return ["Checking local memory...", "Looking for precise matches...", "Preparing concise answer..."];
  }
  return ["Searching local memory...", "Checking related events...", "Preparing answer..."];
}

function detectPendingStyle(message: string) {
  const text = message.toLowerCase();
  if (
    (text.includes("jira") || text.includes("ticket") || text.includes("email") || text.includes("pull request") || text.includes(" pr ")) &&
    ["create", "make", "draft", "prepare", "send", "write", "open", "raise"].some((word) => text.includes(word))
  ) {
    return "task";
  }
  if (["why", "root cause", "cause", "failed", "failure", "error", "exception", "bug", "issue", "problem", "incident", "broke", "not working"].some((term) => text.includes(term))) {
    return "root_cause";
  }
  if (["summarize", "summary", "overview", "what did i work on", "report"].some((term) => text.includes(term))) {
    return "summary";
  }
  if (
    ["did i", "have i", "ever", "saved", "search", "searched", "find", "went through", "gone through"].some((term) => text.includes(term))
  ) {
    return "memory_lookup";
  }
  return "normal";
}
