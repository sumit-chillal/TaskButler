/**
 * Sanitises a single rendered transcript message.
 * Mirrors backend src/utils/text_filters.sanitize_transcript_text so a tool-
 * call markup never reaches the human eye even if the LLM leaks it.
 */
const ANY_TAG = /<[^>\n]+>/g;
const FUNCTION_TAG_PAIR = /<function=[^>]*>[\s\S]*?<\/function>/gi;
const FUNCTION_TAG_OPEN = /<\/?function[^>]*>/gi;
const TOOL_MESSAGE_LINE = /ToolMessage[^\n]*/gi;
const JSON_OBJECT = /\{[^{}]*\}/g;

export function sanitizeTranscript(text: string): string {
  if (!text) return "";
  const stripped = text.trim();
  const isWholeMarkup =
    (stripped.startsWith("<") && stripped.endsWith(">")) ||
    (stripped.startsWith("{") && stripped.endsWith("}")) ||
    stripped.toLowerCase().startsWith("toolmessage");
  if (isWholeMarkup) return "[tool executed]";
  let s = text
    .replace(FUNCTION_TAG_PAIR, "")
    .replace(FUNCTION_TAG_OPEN, "")
    .replace(ANY_TAG, "")
    .replace(JSON_OBJECT, "")
    .replace(TOOL_MESSAGE_LINE, "")
    .replace(/\s{2,}/g, " ");
  return s.trim();
}
