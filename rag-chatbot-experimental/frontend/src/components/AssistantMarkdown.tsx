import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

import { prepareAssistantContent } from "../utils/assistantContent";

interface AssistantMarkdownProps {
  content: string;
  hasStructuredSources: boolean;
}

export function AssistantMarkdown({ content, hasStructuredSources }: AssistantMarkdownProps) {
  const preparedContent = prepareAssistantContent(content, hasStructuredSources);

  return (
    <div className="assistant-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        skipHtml
        components={{
          a: ({ node: _node, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          )
        }}
      >
        {preparedContent}
      </ReactMarkdown>
    </div>
  );
}
