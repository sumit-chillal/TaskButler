"use client";

import type { VoiceGender } from "../lib/types";

interface Props {
  value: VoiceGender;
  onChange: (g: VoiceGender) => void;
}

const OPTIONS: { value: VoiceGender; label: string }[] = [
  { value: "female", label: "Lyra" },
  { value: "male", label: "Atlas" },
];

export const VoiceGenderToggle: React.FC<Props> = ({ value, onChange }) => {
  return (
    <div
      role="radiogroup"
      aria-label="Voice"
      className="glass-soft inline-flex p-1 relative"
      data-testid="voice-gender-toggle"
      style={{ borderRadius: 999 }}
    >
      {/* liquid pill indicator */}
      <span
        aria-hidden
        className="absolute top-1 bottom-1 transition-all duration-500 ease-[var(--ease-glass)]"
        style={{
          left: value === "female" ? 4 : "calc(50% + 0px)",
          width: "calc(50% - 4px)",
          borderRadius: 999,
          background:
            "linear-gradient(180deg, var(--hl-faint), var(--hl-mist))",
          boxShadow:
            "inset 0 1px 0 var(--hl-soft), 0 4px 14px -4px var(--shade-soft)",
        }}
      />
      {OPTIONS.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          data-testid={`voice-${o.value}`}
          onClick={() => onChange(o.value)}
          className="relative z-10 px-4 py-1.5 text-xs tracking-wider uppercase font-mono transition-colors"
          style={{
            color: value === o.value ? "var(--ink-1)" : "var(--ink-3)",
          }}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
};

export default VoiceGenderToggle;
