import type { ChatMessage } from "../types/chat";
import { AssistantMarkdown } from "./AssistantMarkdown";
import { SourcesPanel } from "./SourcesPanel";

interface ChatMessageProps {
  message: ChatMessage;
}

export function ChatMessageView({ message }: ChatMessageProps) {
  const classes = ["message", `message-${message.role}`];
  if (message.isError) {
    classes.push("message-error");
  }

  return (
    <article className={classes.join(" ")}>
      <div className="message-bubble">
        {message.role === "assistant" && !message.isError ? (
          <AssistantMarkdown
            content={message.content}
            hasStructuredSources={Boolean(message.sources?.length)}
          />
        ) : (
          <p>{message.content}</p>
        )}
        {message.intent ? (
          <div className="message-meta">
            <span>{message.intent}</span>
            {message.provider ? <span>{message.provider}</span> : null}
          </div>
        ) : null}
      </div>
      {message.sources && message.sources.length > 0 ? <SourcesPanel sources={message.sources} /> : null}
    </article>
  );
}
