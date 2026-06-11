import { MessageCircle, RotateCcw, ShieldCheck, X } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { sendChatMessage, resetConversation } from "../services/chatApi";
import type { ChatMessage, WidgetTheme } from "../types/chat";
import { ChatInput } from "./ChatInput";
import { ChatMessageView } from "./ChatMessage";
import { TypingIndicator } from "./TypingIndicator";

interface ChatWidgetProps {
  apiBaseUrl?: string;
  title?: string;
  providerLabel?: string;
  compact?: boolean;
  theme?: WidgetTheme;
  embed?: boolean;
}

const DEMO_AUTH_UI_ENABLED = import.meta.env.VITE_AUTH_DEMO_ENABLED === "true";
const RUNTIME_MODE = import.meta.env.VITE_RUNTIME_MODE === "sharepoint" ? "sharepoint" : "local";
const SHOW_DEMO_AUTH_UI = RUNTIME_MODE === "local" && DEMO_AUTH_UI_ENABLED;

export function ChatWidget({
  apiBaseUrl,
  title = "Assistant documentaire",
  providerLabel,
  compact = false,
  theme = "default",
  embed = false
}: ChatWidgetProps) {
  const welcomeMessage: ChatMessage = useMemo(
    () => ({
      id: "welcome",
      role: "assistant",
      content: "Bonjour. Je peux vous aider à retrouver une information dans les documents internes."
    }),
    []
  );
  const [isOpen, setIsOpen] = useState(true);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([welcomeMessage]);
  const [isLoading, setIsLoading] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);
  const [isDemoAuthEnabled, setIsDemoAuthEnabled] = useState(SHOW_DEMO_AUTH_UI);
  const [demoAuthToken, setDemoAuthToken] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const activeDemoToken = SHOW_DEMO_AUTH_UI && isDemoAuthEnabled ? demoAuthToken : undefined;

  const subtitle = useMemo(() => {
    if (!messages.length) {
      return "Prêt";
    }
    const last = messages[messages.length - 1];
    if (last.provider) {
      return `${providerLabel || `Provider ${last.provider}`}${last.usedRag ? " · RAG" : ""}`;
    }
    return providerLabel || "Mode conversationnel";
  }, [messages, providerLabel]);

  async function handleSend(content: string) {
    if (SHOW_DEMO_AUTH_UI && isDemoAuthEnabled && !demoAuthToken.trim()) {
      appendErrorMessage("Veuillez saisir le token de démonstration.");
      return;
    }

    const userMessage: ChatMessage = {
      id: createId(),
      role: "user",
      content
    };
    setMessages((current) => [...current, userMessage]);
    setIsLoading(true);
    setResetError(null);

    try {
      const response = await sendChatMessage({
        conversation_id: conversationId,
        message: content,
        mode: "auto"
      }, apiBaseUrl, activeDemoToken);
      setConversationId(response.conversation_id);
      const assistantMessage: ChatMessage = {
        id: createId(),
        role: "assistant",
        content: response.answer,
        intent: response.intent,
        usedRag: response.used_rag,
        provider: response.provider,
        sources: response.sources
      };
      setMessages((current) => [...current, assistantMessage]);
      queueScroll();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Erreur inconnue.";
      appendErrorMessage(message);
    } finally {
      setIsLoading(false);
      queueScroll();
    }
  }

  async function handleNewConversation() {
    setResetError(null);
    if (conversationId) {
      try {
        await resetConversation(conversationId, apiBaseUrl, activeDemoToken);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Réinitialisation impossible.";
        setResetError(message);
      }
    }
    setConversationId(null);
    setMessages([{ ...welcomeMessage, id: createId() }]);
  }

  function queueScroll() {
    window.setTimeout(() => {
      listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
    }, 50);
  }

  function appendErrorMessage(content: string) {
    setMessages((current) => [
      ...current,
      {
        id: createId(),
        role: "assistant",
        content,
        isError: true
      }
    ]);
    queueScroll();
  }

  return (
    <div className="chat-shell" data-open={isOpen} data-embed={embed} data-compact={compact} data-theme={theme}>
      {isOpen ? (
        <section className="chat-panel" aria-label="Assistant documentaire">
          <header className="chat-header">
            <div>
              <h1>{title}</h1>
              <p>{subtitle}</p>
            </div>
            <div className="chat-header-actions">
              <button className="icon-button" type="button" onClick={handleNewConversation} aria-label="Nouvelle conversation" title="Nouvelle conversation">
                <RotateCcw size={18} />
              </button>
              {!embed ? (
                <button className="icon-button" type="button" onClick={() => setIsOpen(false)} aria-label="Fermer" title="Fermer">
                  <X size={18} />
                </button>
              ) : null}
            </div>
          </header>

          {SHOW_DEMO_AUTH_UI ? (
            <div className="demo-auth-panel">
              <label className="demo-auth-toggle">
                <input
                  type="checkbox"
                  checked={isDemoAuthEnabled}
                  onChange={(event) => setIsDemoAuthEnabled(event.target.checked)}
                />
                <ShieldCheck size={16} />
                <span>Mode démo authentifié</span>
              </label>
              {isDemoAuthEnabled ? (
                <label className="demo-auth-token">
                  <span>Token de démonstration</span>
                  <input
                    type="password"
                    value={demoAuthToken}
                    onChange={(event) => setDemoAuthToken(event.target.value)}
                    placeholder="Saisir le token fourni"
                    autoComplete="off"
                  />
                </label>
              ) : null}
            </div>
          ) : null}

          {resetError ? <div className="chat-alert">{resetError}</div> : null}

          <div className="message-list" ref={listRef}>
            {messages.map((message) => (
              <ChatMessageView key={message.id} message={message} />
            ))}
            {isLoading ? <TypingIndicator /> : null}
          </div>

          <ChatInput disabled={isLoading} onSend={handleSend} />
        </section>
      ) : (
        <button className="chat-launcher" type="button" onClick={() => setIsOpen(true)} aria-label="Ouvrir l'assistant documentaire">
          <MessageCircle size={24} />
        </button>
      )}
    </div>
  );
}

function createId(): string {
  if ("randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
