const THINK_BLOCK = /<think\b[^>]*>[\s\S]*?<\/think>/gi;
const UNFINISHED_THINK_BLOCK = /<think\b[^>]*>[\s\S]*$/gi;
const THINKING_LINE = /^\s*thinking\s*[:=].*$/gim;
const TRAILING_SOURCES_SECTION =
  /\n+(?:#{1,6}\s*)?(?:\*\*)?sources?(?:\s+utilis(?:ée|ées|e|es))?\s*:(?:\*\*)?[^\n]*(?:\n[\s\S]*)?$/i;

export function prepareAssistantContent(content: string, hasStructuredSources: boolean): string {
  let cleaned = stripInternalReasoning(content);
  if (hasStructuredSources) {
    cleaned = cleaned.replace(TRAILING_SOURCES_SECTION, "").trim();
  }
  return cleaned;
}

export function stripInternalReasoning(content: string): string {
  return content
    .replace(THINK_BLOCK, "")
    .replace(UNFINISHED_THINK_BLOCK, "")
    .replace(THINKING_LINE, "")
    .trim();
}
