import { SendHorizontal } from "lucide-react";
import { KeyboardEvent, useState } from "react";

interface ChatInputProps {
  disabled: boolean;
  onSend: (message: string) => void;
}

export function ChatInput({ disabled, onSend }: ChatInputProps) {
  const [value, setValue] = useState("");

  function submit() {
    const message = value.trim();
    if (!message || disabled) {
      return;
    }
    setValue("");
    onSend(message);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form className="chat-input-row" onSubmit={(event) => { event.preventDefault(); submit(); }}>
      <textarea
        value={value}
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Posez une question documentaire..."
        rows={1}
        aria-label="Message"
      />
      <button className="send-button" type="submit" disabled={disabled || !value.trim()} aria-label="Envoyer" title="Envoyer">
        <SendHorizontal size={18} />
      </button>
    </form>
  );
}
