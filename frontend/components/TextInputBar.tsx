"use client";

import { useState } from "react";
import { Send, Sparkles } from "lucide-react";

interface Props {
  onSend: (text: string) => void | Promise<void>;
  disabled?: boolean;
  placeholder?: string;
}

export const TextInputBar: React.FC<Props> = ({
  onSend,
  disabled,
  placeholder = "Ask, plan, remember…",
}) => {
  const [value, setValue] = useState("");

  async function submit(e?: React.FormEvent) {
    e?.preventDefault();
    if (!value.trim() || disabled) return;
    const v = value;
    setValue("");
    await onSend(v);
  }

  return (
    <form
      onSubmit={submit}
      className="glass relative flex items-center gap-2 px-3 py-2"
      data-testid="text-input-bar"
    >
      <Sparkles
        size={14}
        aria-hidden
        style={{ color: "var(--ink-accent)", marginLeft: 4 }}
      />
      <input
        data-testid="text-input"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="flex-1 bg-transparent outline-none px-1 py-2 placeholder:text-[var(--ink-3)] disabled:opacity-50"
        style={{ color: "var(--ink-1)", caretColor: "var(--ink-accent)" }}
      />
      <button
        data-testid="text-send-btn"
        type="submit"
        disabled={disabled || !value.trim()}
        aria-label="Send message"
        className="rounded-full px-4 py-2 inline-flex items-center gap-2 text-xs font-medium tracking-wider uppercase transition-colors disabled:opacity-40"
        style={{
          background:
            "linear-gradient(180deg, rgba(var(--tint-todo),0.95), rgba(var(--tint-todo),0.7))",
          color: "var(--bg-base)",
          boxShadow:
            "inset 0 1px 0 var(--hl-mid), 0 6px 22px -6px rgba(var(--tint-todo),0.55)",
        }}
      >
        <Send size={12} />
        Send
      </button>
    </form>
  );
};

export default TextInputBar;
